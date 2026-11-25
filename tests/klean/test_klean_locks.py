"""Locks between klean processes (klean/locks.py and where klean uses them), with real child
processes racing: live runs, stopping, data installs, pip, the plugin build, KIS accounts."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[2]
sys.path[:0] = [str(_HERE.parent), str(REPO)]

from klean import live, locks, projects
from klean.workspace import KleanError, Workspace

DAYS = ["2026-09-22", "2026-09-23", "2026-09-28", "2026-09-29", "2026-09-30"]

PRELUDE = f"""
import json, os, sys, time
sys.path.insert(0, {str(REPO)!r})
from pathlib import Path
from unittest import mock
from klean import live, locks, projects
from klean.workspace import Workspace
mock.patch("klean.results.is_demo_data", return_value=False).start()
"""


def child(code: str, env: dict | None = None) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", PRELUDE + textwrap.dedent(code)], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env={**os.environ, **(env or {})})


def wait_for(path: Path, seconds: float = 20) -> None:
    deadline = time.time() + seconds
    while not path.exists():
        if time.time() > deadline:
            raise AssertionError(f"{path} didn't appear")
        time.sleep(0.05)


class LockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def holder(self, lock: Path, shared: bool = False) -> subprocess.Popen:
        ready = self.dir / f"ready-{time.time_ns()}"
        p = child(f"""
            with locks.hold(Path({str(lock)!r}), "test holder", shared={shared}):
                Path({str(ready)!r}).touch()
                time.sleep(60)
            """)
        self.addCleanup(p.stdout.close)
        self.addCleanup(lambda: p.poll() is None and (p.kill() or p.wait()))
        wait_for(ready)
        return p

    def test_busy_names_the_holder_and_a_killed_holder_lets_go(self):
        lock = self.dir / "a.lock"
        p = self.holder(lock)
        with self.assertRaises(locks.Busy) as e:
            with locks.hold(lock, "me", wait=False):
                pass
        self.assertEqual(e.exception.holder["pid"], p.pid)
        self.assertIn(f"pid {p.pid} (test holder", str(e.exception))
        with self.assertRaisesRegex(locks.Busy, "still busy after 0 s"):
            with locks.hold(lock, "me", timeout=0.3):
                pass
        p.send_signal(signal.SIGKILL)                       # a crash: the system lets the lock go
        p.wait()
        with locks.hold(lock, "me", wait=False):
            pass

    def test_shared_and_exclusive(self):
        lock = self.dir / "data.lock"
        p = self.holder(lock, shared=True)
        with locks.hold(lock, "another reader", shared=True, wait=False):
            pass
        with self.assertRaises(locks.Busy):
            with locks.hold(lock, "a writer", wait=False):
                pass
        p.kill()
        p.wait()
        with locks.hold(lock, "a writer", wait=False):
            pass

    def test_works_in_a_normal_folder(self):
        self.assertTrue(locks.works_in(self.dir))

    def test_processes_checking_a_folder_at_once_all_find_locks_work(self):
        """(CI found it: with one shared probe file, a process checking while another held the probe
        concluded "locks don't work" and ran unlocked.)"""
        folder, go = self.dir / "shared", self.dir / "go"
        folder.mkdir()
        kids = [child(f"""
            while not Path({str(go)!r}).exists():
                time.sleep(0.001)
            print("WORKS" if locks.works_in(Path({str(folder)!r})) else "BROKEN")
            """) for _ in range(8)]
        time.sleep(1.0)                                   # all started and waiting
        go.touch()
        outs = [k.communicate(timeout=30)[0] for k in kids]
        self.assertEqual([o.split()[-1] for o in outs], ["WORKS"] * 8, outs)
        self.assertEqual(list(folder.iterdir()), [])          # no probe files left

    def test_replace_is_never_half_a_file(self):
        """A reader sees one whole version or the other while krx-lean's install rewrites files."""
        from krx_lean import lean_install
        src_a, src_b, dst = self.dir / "a", self.dir / "b", self.dir / "dst"
        for d, byte, size in ((src_a, b"a", 3_000_000), (src_b, b"b", 4_000_000)):
            (d / "equity").mkdir(parents=True)
            (d / "equity" / "x.zip").write_bytes(byte * size)
        lean_install.sync_tree(src_a, dst)
        writer = child(f"""
            sys.path.insert(0, {str(REPO)!r})
            from krx_lean import lean_install
            for i in range(30):
                src = Path({str(src_b)!r}) if i % 2 == 0 else Path({str(src_a)!r})
                os.utime(src / "equity" / "x.zip", (i, i))            # always "changed": copied every time
                lean_install.sync_tree(src, Path({str(dst)!r}))
            """)
        seen = set()
        while writer.poll() is None:
            data = (dst / "equity" / "x.zip").read_bytes()
            self.assertIn((data[:1], len(data)), {(b"a", 3_000_000), (b"b", 4_000_000)})
            seen.add(data[:1])
        out = writer.communicate()[0]
        self.assertEqual(writer.returncode, 0, out)
        self.assertEqual([p.name for p in (dst / "equity").iterdir()], ["x.zip"])     # no temporary files left


class LiveLockTest(unittest.TestCase):
    """Two `klean live run`s of one deployment (cron, `update data`, the GUI) never overlap."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.home = root / "home"
        self.home.mkdir()
        self.ws = self.make_ws(root / "ws", root / "Lean")
        self.project = projects.create(self.ws, "P", "python", "buy-hold")
        p = mock.patch("klean.results.is_demo_data", return_value=False)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def make_ws(root: Path, lean: Path) -> Workspace:
        ws = Workspace(root=root, lean_root=str(lean))
        index = ws.data / "index" / "krx" / "daily"
        index.mkdir(parents=True)
        with zipfile.ZipFile(index / "kospi.zip", "w") as z:
            z.writestr("kospi.csv", "".join(f"{d.replace('-', '')} 00:00,1,1,1,1,0\n" for d in DAYS))
        ws.save()
        return ws

    def runner(self, dep: Path, log: Path, seconds: float = 0.4) -> subprocess.Popen:
        """`live.run` in a child process; each trading day takes ``seconds`` and is logged."""
        return child(f"""
            dep, logf = Path({str(dep)!r}), Path({str(log)!r})
            def fake_session(ws, d, session, log=print, timeout=900, now=False):
                with open(logf, "a") as f:
                    f.write(f"{{os.getpid()}} {{session}}\\n")
                time.sleep({seconds})
                book = live.ledger(d)
                book["last_session"] = session
                (d / live.LEDGER).write_text(json.dumps(book))
                return {{"session": session, "ok": True}}
            with mock.patch.object(live, "ensure_plugin"), mock.patch.object(live, "run_session", side_effect=fake_session):
                live.run(Workspace.load(Path({str(self.ws.root)!r})), dep)
            """, env={"HOME": str(self.home)})

    def test_two_runs_one_deployment_each_day_once(self):
        dep = live.deploy(self.ws, self.project, start="2026-09-23")
        log = self.ws.root / "sessions.log"
        a = self.runner(dep, log)
        wait_for(log)                                       # a holds the deployment
        b = self.runner(dep, log)
        out_b = b.communicate(timeout=30)[0]
        a.communicate(timeout=30)
        self.assertIn("skipped, already being run by pid", out_b)
        days = [line.split()[1] for line in log.read_text().splitlines()]
        self.assertEqual(days, DAYS[1:])                    # every pending day once, in order
        self.assertEqual({line.split()[0] for line in log.read_text().splitlines()}, {str(a.pid)})

    def test_stop_while_running_stops_after_the_current_day(self):
        dep = live.deploy(self.ws, self.project, start="2026-09-23")
        log = self.ws.root / "sessions.log"
        a = self.runner(dep, log, seconds=1.0)
        wait_for(log)
        record = live.stop(dep, log=lambda *x: None)
        self.assertTrue(record["stopping"])
        self.assertEqual(live.load(dep)["status"], "running")     # not yet
        a.communicate(timeout=30)
        self.assertEqual(live.load(dep)["status"], "stopped")
        self.assertEqual(len(log.read_text().splitlines()), 1)    # the day in progress, no more
        self.assertFalse((dep / live.STOP_REQUEST).exists())
        self.assertNotIn("stopping", live.stop(dep))               # idle: stops at once

    def test_a_live_day_holds_the_data_and_install_waits(self):
        dep = live.deploy(self.ws, self.project, start="2026-09-30")
        log = self.ws.root / "sessions.log"
        a = self.runner(dep, log, seconds=1.5)
        wait_for(log)
        started = time.monotonic()
        with locks.hold(locks.data_lock(self.ws.root), "installing KRX data"):
            waited = time.monotonic() - started
        a.communicate(timeout=30)
        self.assertGreater(waited, 0.8)                     # the install waited for the day to finish

    def test_one_kis_account_one_deployment_across_workspaces(self):
        fake = mock.MagicMock()
        fake.return_value.account_id.return_value = "50******-01 paper abc"
        fake.return_value.balance.return_value = {"total": 100_000_000, "cash": 100_000_000, "holdings": []}
        other_ws = self.make_ws(self.ws.root.parent / "ws2", Path(self.ws.lean_root))
        other = projects.create(other_ws, "Q", "python", "buy-hold")
        with mock.patch("klean.kis.Kis", fake):
            first = live.deploy(self.ws, self.project, broker="kis-paper")
            with self.assertRaisesRegex(KleanError, r"P/.* already trades this KIS account"):
                live.deploy(other_ws, other, broker="kis-paper")            # another workspace
            claims = json.loads(live.kis_claims_path().read_text())
            self.assertEqual(claims["50******-01 paper abc"]["deployment"], str(first))
            live.stop(first)                                                 # releases the account
            self.assertEqual(json.loads(live.kis_claims_path().read_text()), {})
            second = live.deploy(other_ws, other, broker="kis-paper")
            self.assertEqual(live.load(second)["kis_account"], "50******-01 paper abc")

    def test_two_kis_deploys_at_once_one_wins(self):
        code = f"""
            fake = mock.MagicMock()
            fake.return_value.account_id.return_value = "50******-01 paper abc"
            fake.return_value.balance.side_effect = lambda: time.sleep(0.5) or {{"total": 1e8, "cash": 1e8, "holdings": []}}
            ws = Workspace.load(Path({str(self.ws.root)!r}))
            with mock.patch("klean.kis.Kis", fake):
                try:
                    print("DEPLOYED", live.deploy(ws, ws.root / "P", broker="kis-paper"))
                except Exception as e:
                    print("REFUSED", e)
            """
        a, b = child(code, {"HOME": str(self.home)}), child(code, {"HOME": str(self.home)})
        outs = [a.communicate(timeout=30)[0], b.communicate(timeout=30)[0]]
        self.assertEqual(sorted(o.split()[0] for o in outs), ["DEPLOYED", "REFUSED"], outs)
        self.assertIn("already trades this KIS account", next(o for o in outs if o.startswith("REFUSED")))
        self.assertEqual(len(live.deployments(self.project)), 1)


class InstallLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def test_pip_one_at_a_time_and_skipped_when_nothing_changed(self):
        venv, site = self.dir / "venv", self.dir / "site"
        venv.mkdir()
        site.mkdir()
        spans = self.dir / "spans.log"
        code = f"""
            from klean import backtest
            def fake_pip(cmd, **kw):
                t = time.time()
                time.sleep(0.6)
                (Path({str(site)!r}) / f"pkg-{{os.getpid()}}").mkdir()      # pip changes site-packages
                with open({str(spans)!r}, "a") as f:
                    f.write(f"{{t}} {{time.time()}}\\n")
            ws = mock.Mock(python_venv={str(venv)!r})
            req = Path({str(self.dir)!r}) / f"req-{{os.getpid()}}.txt"
            req.write_text(f"pkg{{os.getpid()}}\\n")
            with mock.patch.object(backtest, "run", side_effect=fake_pip), \\
                 mock.patch.object(backtest, "site_packages", return_value={str(site)!r}):
                print("RAN", backtest.install_requirements(ws, req, log=print))
                print("AGAIN", backtest.install_requirements(ws, req, log=print))
            """
        a, b = child(code), child(code)
        outs = a.communicate(timeout=30)[0] + b.communicate(timeout=30)[0]
        self.assertEqual(outs.count("RAN True"), 2, outs)
        (s1, e1), (s2, e2) = sorted(tuple(map(float, line.split())) for line in spans.read_text().splitlines())
        self.assertLessEqual(e1, s2)                        # never at the same time
        self.assertIn("klean: waiting for ", outs)            # the second one waited (and said so)
        # the second call of each process: the other one's install changed site-packages after the
        # first's stamp, so one of them re-runs; nothing changed after the last: skipped
        self.assertGreaterEqual(outs.count("AGAIN False"), 1, outs)

    def test_plugin_built_once(self):
        launcher = self.dir / "Lean" / "Launcher" / "bin" / "Release"
        launcher.mkdir(parents=True)
        engine = launcher / "QuantConnect.Lean.Engine.dll"
        engine.write_text("")
        os.utime(engine, (1, 1))
        builds = self.dir / "builds.log"
        code = f"""
            def fake_build(cmd, **kw):
                out = Path(cmd[cmd.index("-o") + 1])
                time.sleep(0.6)
                out.mkdir(parents=True, exist_ok=True)
                (out / live.PLUGIN_DLL).write_text("built")
                with open({str(builds)!r}, "a") as f:
                    f.write(f"{{os.getpid()}}\\n")
            ws = mock.Mock(root=Path({str(self.dir)!r}), launcher_dir=Path({str(launcher)!r}))
            with mock.patch.object(live, "run_command", side_effect=fake_build), \\
                 mock.patch.object(live, "dotnet", return_value="dotnet"):
                print(live.ensure_plugin(ws, log=print))
            """
        a, b = child(code), child(code)
        outs = a.communicate(timeout=30)[0] + b.communicate(timeout=30)[0]
        self.assertEqual(len(builds.read_text().splitlines()), 1, outs)        # the second found it built
        self.assertEqual((launcher / live.PLUGIN_DLL).read_text(), "built")
        self.assertEqual([p.name for p in self.dir.joinpath(".klean").glob("plugin-build*")], [])


if __name__ == "__main__":
    unittest.main()
