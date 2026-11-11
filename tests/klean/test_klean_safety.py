import io
import contextlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parent), str(_HERE.parents[2])]   # tests/klean (helpers) and the repo root

from klean import backtest, cli, results
from klean.workspace import KleanError, Workspace


class SafetyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.ws = Workspace(root=self.root / "ws", lean_root=str(self.root / "Lean"))
        self.ws.data.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_zip_entries_outside_the_workspace_are_refused(self):
        for bad in ("../evil.txt", "data/../../evil.txt", "/tmp/klean-evil.txt"):
            z = self.root / "bad.zip"
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("data/equity/krx/ok.txt", "ok")
                f.writestr(bad, "evil")
            with self.assertRaises(KleanError):
                cli.install_data(self.ws, zip_path=z)
            self.assertFalse((self.root / "evil.txt").exists())
            self.assertFalse((self.ws.data / "equity" / "krx" / "ok.txt").exists())   # nothing unzipped

    def test_run_folders_are_unique(self):
        project = self.ws.root / "P"
        with mock.patch.object(backtest.dt, "datetime") as fake:
            fake.now.return_value.strftime.return_value = "2026-11-10_10-00-00"
            a = backtest.results_folder(project, None, "x")
            b = backtest.results_folder(project, None, "x")
            c = backtest.results_folder(project, None, "x")
        self.assertEqual([p.name for p in (a, b, c)],
                         ["2026-11-10_10-00-00_x", "2026-11-10_10-00-00_x-2", "2026-11-10_10-00-00_x-3"])
        self.assertTrue(all(p.is_dir() for p in (a, b, c)))

    def test_timeout_stops_the_run_and_marks_it_failed(self):
        launcher = Path(self.ws.lean_root) / "Launcher" / "bin" / "Release"
        launcher.mkdir(parents=True)
        (launcher / "config.json").write_text("{}")
        project = self.ws.root / "P"
        project.mkdir(parents=True)
        (project / "main.py").write_text("pass\n")
        run_dir = project / "backtests" / "r1"
        sleeper = [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(60)"]
        with mock.patch.object(backtest, "launcher_args", lambda *a, **k: sleeper), \
                mock.patch.object(backtest, "git_commit", lambda p: ""), contextlib.redirect_stdout(io.StringIO()):
            r = backtest.run_once(self.ws, project, "python", project / "main.py", "A", {}, run_dir, {}, {},
                                  timeout=1)
        self.assertFalse(r["ok"])
        self.assertIn("timed out after 1 s", r["error"])
        self.assertIn("time limit", (run_dir / "console.txt").read_text())
        self.assertEqual(results.run_error(run_dir), "timed out after 1 s (--timeout)")   # from the manifest


if __name__ == "__main__":
    unittest.main()
