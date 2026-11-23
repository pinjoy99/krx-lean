"""Forward tests (klean/forward.py): freezing, dates, refreshes, stop; the GUI's live API."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parent), str(_HERE.parents[2])]

from klean import forward, gui, projects
from klean.workspace import KleanError, Workspace


def fake_backtest(ws, code, parameters, *, output, backtest_name="", timeout=0):
    """What klean.backtest.backtest leaves behind, without LEAN: a summary and an equity chart
    starting on the requested date."""
    import datetime as dt
    output.mkdir(parents=True)
    start = dt.datetime.fromisoformat(parameters["start_date"]).replace(tzinfo=dt.timezone.utc).timestamp()
    if parameters.get("ignore_period"):
        start -= 400 * 86400
    (output / "A-summary.json").write_text(json.dumps({"statistics": {"End Equity": "1100", "Net Profit": "10%"},
                                                       "state": {"Status": "Completed"}}))
    (output / "A.json").write_text(json.dumps({"charts": {"Strategy Equity": {"series": {"Equity": {
        "values": [[int(start), 1000, 1000, 1000, 1000], [int(start) + 86400, 1100, 1100, 1100, 1100]]}}}}}))
    FakeRuns.calls.append(parameters)
    return {"results": str(output)}


class FakeRuns:
    calls: list = []


class ForwardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.ws = Workspace(root=root / "ws", lean_root=str(root / "Lean"))
        self.ws.data.mkdir(parents=True)
        self.ws.save()
        self.project = projects.create(self.ws, "P", "python", "buy-hold")
        self.last = "20260930"
        patches = [mock.patch("klean.results.last_data_date", side_effect=lambda ws: self.last),
                   mock.patch("klean.backtest.backtest", side_effect=fake_backtest),
                   mock.patch("klean.results.is_demo_data", return_value=False)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        FakeRuns.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def test_templates_take_their_period_from_parameters(self):
        for language in ("python", "csharp"):
            for template in projects.TEMPLATES:
                p = projects.create(self.ws, f"T{language[0]}{template.replace('-', '')}", language, template)
                self.assertTrue(forward.uses_period(p), (language, template))

    def test_start_freezes_the_code_from_the_next_day(self):
        test = forward.start(self.ws, self.project, "first", {"code": "005930", "start_date": "2000-01-01"})
        record = forward.load(test)
        self.assertEqual((record["start_date"], record["backdated"]), ("2026-10-01", False))
        self.assertEqual(record["parameters"], {"code": "005930"})     # its own period wins
        self.assertTrue((test / "code" / "main.py").exists())
        (self.project / "main.py").write_text("# changed after the start\n")
        self.assertNotIn("changed after", (test / "code" / "main.py").read_text())
        # no data after the start yet: nothing to run
        self.assertIn("waiting for data", forward.refresh(self.ws, test)["skipped"])
        self.assertEqual(forward.summary(self.ws, test)["state"], "waiting for data")
        self.assertEqual(FakeRuns.calls, [])
        # new days arrive: it runs from its start to the latest data, with its parameters
        self.last = "20261009"
        entry = forward.refresh(self.ws, test)
        self.assertTrue(entry["ok"], entry)
        self.assertEqual(FakeRuns.calls[-1], {"code": "005930", "start_date": "2026-10-01", "end_date": "2026-10-09"})
        sm = forward.summary(self.ws, test)
        self.assertEqual((sm["state"], sm["stats"]["End Equity"], sm["refreshes"]), ("running", "1100", 1))
        self.assertTrue(sm["ref"].endswith("/live/" + test.name + "/run"))

    def test_backdated_and_stop(self):
        test = forward.start(self.ws, self.project, start_date="2026-06-01")
        self.assertTrue(forward.load(test)["backdated"])
        self.assertTrue(forward.refresh(self.ws, test)["ok"])
        forward.stop(test)
        self.assertEqual(forward.refresh(self.ws, test), {"skipped": "stopped"})
        self.assertEqual(forward.summary(self.ws, test)["state"], "stopped")
        log = []
        self.assertEqual(forward.refresh_all(self.ws, log=log.append), [])   # stopped ones are left alone

    def test_code_that_sets_its_own_dates_is_refused(self):
        main = self.project / "main.py"
        main.write_text(main.read_text().replace('set_period(self, "2024-01-02")', "self.set_start_date(2024, 1, 2)"))
        with self.assertRaisesRegex(KleanError, "sets its own dates"):
            forward.start(self.ws, self.project)
        self.assertEqual(forward.tests(self.project), [])                  # nothing left behind

    def test_a_run_that_ignores_the_start_date_fails(self):
        test = forward.start(self.ws, self.project, parameters={"ignore_period": "1"}, start_date="2026-06-01")
        entry = forward.refresh(self.ws, test)
        self.assertFalse(entry["ok"])
        self.assertIn("doesn't take its period", entry["error"])
        self.assertEqual(forward.summary(self.ws, test)["state"], "failed")
        self.assertFalse((test / "run").exists())

    def test_refresh_all_after_a_data_update(self):
        forward.start(self.ws, self.project, start_date="2026-06-01")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            done = forward.refresh_all(self.ws)
        self.assertEqual(len(done), 1)
        self.assertIn("end equity 1100", out.getvalue())

    def test_gui_live_api(self):
        test = forward.start(self.ws, self.project, "g", start_date="2026-06-01")
        forward.refresh(self.ws, test)
        w = gui.api_workspace(self.ws, {})
        row = next(p for p in w["projects"] if p["name"] == "P")
        self.assertEqual((row["live_runs"], row["last_live"]["id"], row["last_live"]["state"]), (1, test.name, "running"))
        live = gui.api_live(self.ws, {"project": ["P"]})
        self.assertTrue(live["uses_period"])
        self.assertEqual([t["id"] for t in live["tests"]], [test.name])
        detail = gui.api_live_test(self.ws, {"project": ["P"], "id": [test.name]})
        self.assertEqual(len(detail["history"]), 1)
        gui.api_live_stop(self.ws, {"project": "P", "id": test.name})
        self.assertEqual(forward.load(test)["status"], "stopped")
        with self.assertRaisesRegex(KleanError, "no forward test"):
            gui.api_live_test(self.ws, {"project": ["P"], "id": ["../x"]})


if __name__ == "__main__":
    unittest.main()
