import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parent), str(_HERE.parents[2])]   # tests/klean (helpers) and the repo root

from klean import optimize, results
from klean.workspace import Workspace, check
from test_klean_p1 import make_run

RUNTIME_ERROR = {"Status": "RuntimeError", "RuntimeError": "[Errno 2] No such file or directory: 'kospi200.zip'",
                 "StackTrace": "  at krx_benchmark\n  in main.py: line 34"}


def set_state(run: Path, state: dict) -> None:
    summary = next(run.glob("*-summary.json"))
    data = json.loads(summary.read_text())
    data["state"] = state
    summary.write_text(json.dumps(data))


class FailedRunTest(unittest.TestCase):
    """A LEAN run that throws in initialize still writes a summary; klean must call it failed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self.tmp.name) / "P"

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_error(self):
        ok = make_run(self.proj, "ok", 110.0, {"Sharpe Ratio": "0.2"})
        set_state(ok, {"Status": "Completed", "RuntimeError": ""})
        self.assertEqual(results.run_error(ok), "")
        old = make_run(self.proj, "old", 110.0, {"Sharpe Ratio": "0.2"})   # summary without a state block
        self.assertEqual(results.run_error(old), "")
        bad = make_run(self.proj, "bad", 100.0, {})
        set_state(bad, RUNTIME_ERROR)
        self.assertIn("No such file or directory", results.run_error(bad))
        self.assertIn("main.py: line 34", results.run_error(bad))
        stopped = make_run(self.proj, "stopped", 100.0, {})
        set_state(stopped, {"Status": "Stopped", "RuntimeError": ""})
        self.assertEqual(results.run_error(stopped), "LEAN reports status Stopped")
        empty = self.proj / "backtests" / "empty"
        empty.mkdir()
        self.assertIn("no *-summary.json", results.run_error(empty))

    def test_optimize_counts_a_crashed_run_as_failed(self):
        bad = make_run(self.proj, "bad", 100.0, {})
        set_state(bad, RUNTIME_ERROR)
        e = optimize.evaluate(bad, "Sharpe Ratio", [])
        self.assertFalse(e["ok"])
        self.assertIn("No such file", e["error"])


class DemoAndDoctorTest(unittest.TestCase):
    def test_demo_marker_and_index_check(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Workspace(root=Path(d), lean_root=str(Path(d) / "Lean"))
            krx = ws.data / "equity" / "krx"
            krx.mkdir(parents=True)
            self.assertFalse(results.is_demo_data(ws))
            rows = {item: (ok, detail) for item, ok, detail in check(ws)}
            self.assertFalse(rows["KOSPI 200 index (benchmark)"][0])
            self.assertIn("klean data install --demo", rows["KOSPI 200 index (benchmark)"][1])
            (krx / results.DEMO_MARKER).write_text("synthetic")
            idx = ws.data / "index" / "krx" / "daily"
            idx.mkdir(parents=True)
            with zipfile.ZipFile(idx / "kospi200.zip", "w") as z:
                z.writestr("kospi200.csv", "20240102 00:00,1,1,1,1,0\n")
            self.assertTrue(results.is_demo_data(ws))
            rows = {item: (ok, detail) for item, ok, detail in check(ws)}
            self.assertTrue(rows["KOSPI 200 index (benchmark)"][0])
            self.assertIn("SYNTHETIC DEMO DATA", rows["KRX daily data"][1])
            self.assertTrue(results.data_status(ws)["synthetic_demo_data"])


if __name__ == "__main__":
    unittest.main()
