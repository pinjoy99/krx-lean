"""KIS-PAPER's pre-open schedule: the live status (next pre-open, missed runs) and `klean schedule`
(lines in the crontab, in the local time zone; hand-made lines kept)."""
import contextlib
import io
import os
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parent), str(_HERE.parents[2])]

from klean import live, projects, schedule
from klean.workspace import Workspace

DAYS = ["2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27"]


def in_tz(name):
    """Run with the computer's time zone set to ``name``."""
    old = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


tz = contextlib.contextmanager(in_tz)


class KisStatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.ws = Workspace(root=root / "ws", lean_root=str(root / "Lean"))
        index = self.ws.data / "index" / "krx" / "daily"
        index.mkdir(parents=True)
        with zipfile.ZipFile(index / "kospi.zip", "w") as z:
            z.writestr("kospi.csv", "".join(f"{d.replace('-', '')} 00:00,1,1,1,1,0\n" for d in DAYS))
        self.ws.save()
        project = projects.create(self.ws, "top10", "python", "buy-hold")
        for p in (mock.patch("klean.results.is_demo_data", return_value=False),):
            p.start()
            self.addCleanup(p.stop)
        self.dep = live.deploy(self.ws, project, "top10", start="2026-11-25")
        record = live.load(self.dep)   # as a KIS-PAPER deployment made Tue 2026-11-24 23:30 EST (Wed 13:30 KST)
        record.update(broker="kis-paper", first_session="2026-11-25", created_utc="2026-11-25T04:30:00Z", backdated=False)
        live.save(self.dep, record)

    def tearDown(self):
        self.tmp.cleanup()

    def at(self, kst):
        return mock.patch.dict(os.environ, {"KLEAN_KIS_NOW": kst})

    def test_missed_pre_opens_and_the_next_one(self):
        with self.at("2026-11-28T04:59"):                       # Saturday: Thursday's and Friday's passed
            sm = live.summary(self.ws, self.dep)
        self.assertEqual(sm["broker"], "kis-paper")
        self.assertEqual(sm["missed_pre_opens"], ["2026-11-26", "2026-11-27"])
        self.assertEqual(sm["state"], "missed 2 pre-open runs")
        self.assertEqual(sm["next_pre_open"], "2026-11-30T08:30:00+09:00")    # Monday
        with self.at("2026-11-25T20:00"):                       # the evening it was made: nothing missed yet
            sm = live.summary(self.ws, self.dep)
        self.assertEqual((sm["state"], sm["missed_pre_opens"]), ("waiting for the pre-open run", []))
        with self.at("2026-11-26T08:40"):                       # during Thursday's pre-open: not missed (yet)
            sm = live.summary(self.ws, self.dep)
        self.assertEqual(sm["missed_pre_opens"], [])
        self.assertEqual(sm["next_pre_open"], "2026-11-26T08:30:00+09:00")

    def test_a_run_clears_older_misses(self):
        book = live.ledger(self.dep)          # Monday's pre-open ran: it traded Friday's session
        book.update(last_session="2026-11-27", equity=[{"session": "2026-11-27", "cash": 1, "holdings_value": 0, "equity": 1e7}])
        (self.dep / live.LEDGER).write_text(__import__("json").dumps(book))
        record = live.load(self.dep)
        record["runs"] = [{"session": "2026-11-27", "ok": True}]
        live.save(self.dep, record)
        with self.at("2026-11-30T09:10"):
            sm = live.summary(self.ws, self.dep)
        self.assertEqual((sm["state"], sm["missed_pre_opens"]), ("running", []))

    def test_paper_deployments_unchanged(self):
        record = live.load(self.dep)
        record["broker"] = "paper"
        live.save(self.dep, record)
        sm = live.summary(self.ws, self.dep)
        self.assertEqual((sm["broker"], sm["state"]), ("paper", "waiting for data"))
        self.assertNotIn("next_pre_open", sm)

    def test_status_note(self):
        from klean import cli
        with self.at("2026-11-28T04:59"):
            note = cli.kis_note("top10/x", live.summary(self.ws, self.dep))
        self.assertIn("next pre-open Mon 2026-11-30 08:30 KST", note)
        self.assertIn("missed: no run at the pre-open of 2026-11-26, 2026-11-27", note)
        self.assertIn("klean schedule install", note)


class ScheduleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.ws = Workspace(root=root / "krx-workspace", lean_root=str(root / "Lean"))
        self.ws.root.mkdir()
        self.cron = ("30 7 * * *  $HOME/bin/krx-update\n"
                     "0 18 * * 1-5 /home/u/projects/other/cron_monitor.sh >> /tmp/x.log 2>&1\n")
        p = mock.patch.object(schedule, "read_crontab", side_effect=lambda: self.cron)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(schedule, "write_crontab", side_effect=lambda text: setattr(self, "cron", text))
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(schedule, "cron_service_note", return_value="cron: running")
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, {"HOME": str(root)})
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_times_in_the_local_zone(self):
        cases = {"America/New_York": (["30 7,8 * * *"], ["35 18,19 * * 0-4"]),
                 "Asia/Seoul": (["30 21 * * *"], ["35 8 * * 1-5"]),
                 "UTC": (["30 12 * * *"], ["35 23 * * 0-4"]),
                 "Europe/Berlin": (["30 13,14 * * *"], ["35 0,1 * * 1-5"])}
        for name, (data, kis) in cases.items():
            with tz(name):
                self.assertEqual(schedule.local_slots(*schedule.JOBS["data"][:2], year=2026), data, name)
                self.assertEqual(schedule.local_slots(*schedule.JOBS["kis"][:2], year=2026), kis, name)

    def test_install_keeps_hand_made_lines_and_is_idempotent(self):
        out = io.StringIO()
        with tz("America/New_York"), contextlib.redirect_stdout(out):
            self.assertTrue(schedule.kis_hint(self.ws))                         # nothing for the pre-open yet
            added = schedule.install(self.ws)
        lines = self.cron.splitlines()
        self.assertEqual(lines[:2], ["30 7 * * *  $HOME/bin/krx-update",          # yours, untouched
                                     "0 18 * * 1-5 /home/u/projects/other/cron_monitor.sh >> /tmp/x.log 2>&1"])
        self.assertEqual(len(added), 1)                                          # the data job is yours already
        self.assertTrue(added[0].startswith("35 18,19 * * 0-4 cd "))
        self.assertIn("-m klean live run", added[0])
        self.assertTrue(added[0].endswith(f"# klean-schedule:kis:{self.ws.root}"))
        self.assertIn("already scheduled by hand", out.getvalue())
        self.assertEqual(len(list((Path(self.tmp.name) / ".klean").glob("crontab.*.bak"))), 1)   # a backup
        with tz("America/New_York"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(schedule.kis_hint(self.ws), "")                    # scheduled now
            schedule.install(self.ws)                                            # again: replaced, not doubled
            self.assertEqual(len(schedule.managed(self.cron, self.ws, "kis")), 1)
            self.assertEqual(schedule.remove(self.ws), 1)
        self.assertEqual(self.cron.splitlines(), lines[:2])

    def test_install_both_and_status(self):
        self.cron = ""
        out = io.StringIO()
        with tz("Asia/Seoul"), contextlib.redirect_stdout(out):
            schedule.install(self.ws)
            st = schedule.status(self.ws)
        self.assertEqual([ln.split(" cd ")[0] for ln in self.cron.splitlines()], ["30 21 * * *", "35 8 * * 1-5"])
        self.assertIn("-m klean update data", self.cron)
        self.assertEqual(len(st["data"]["managed"]), 1)
        self.assertIn("next due:", out.getvalue())

    def test_another_workspace_is_left_alone(self):
        other = Workspace(root=self.ws.root.parent / "other", lean_root=self.ws.lean_root)
        with tz("UTC"), contextlib.redirect_stdout(io.StringIO()):
            self.cron = ""
            schedule.install(other, ("kis",))
            schedule.install(self.ws, ("kis",))
            self.assertEqual(len(self.cron.splitlines()), 2)
            schedule.remove(self.ws)
        self.assertEqual(len(self.cron.splitlines()), 1)
        self.assertIn(str(other.root), self.cron)


if __name__ == "__main__":
    unittest.main()
