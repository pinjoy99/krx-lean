"""The Backtest dashboard's run view: which benchmark a run used (found from its values) and its
maximum drawdown (klean/results.py, klean/gui.py)."""
import datetime as dt
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parent), str(_HERE.parents[2])]

from klean import gui, results
from klean.workspace import Workspace

DAYS = ["20180502", "20180503", "20180504", "20180507"]


def ts(day: str) -> int:                     # LEAN samples at midnight in Korea: 15:00 UTC that day
    return int(dt.datetime.strptime(day, "%Y%m%d").replace(hour=15, tzinfo=dt.timezone.utc).timestamp())


class RunViewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.ws = Workspace(root=root / "ws", lean_root=str(root / "Lean"))
        index = self.ws.data / "index" / "krx" / "daily"
        index.mkdir(parents=True)
        for name, closes in (("kospi200", [330.0, 331.0, 332.0, 333.0]), ("kosdaq", [870.0, 860.0, 880.0, 890.0])):
            with zipfile.ZipFile(index / f"{name}.zip", "w") as z:
                z.writestr(f"{name}.csv", "".join(f"{d} 00:00,1,1,1,{c},0\n" for d, c in zip(DAYS, closes)))
        krx = self.ws.data / "equity" / "krx"
        (krx / "daily").mkdir(parents=True)
        (krx / "factor_files").mkdir()
        with zipfile.ZipFile(krx / "daily" / "a00001.zip", "w") as z:     # a 5:1 split after 05-03
            z.writestr("a00001.csv", "".join(f"{d} 00:00,0,0,0,{c * 10000},1\n"
                                             for d, c in zip(DAYS, [500_000, 510_000, 102_000, 103_000])))
        (krx / "factor_files" / "a00001.csv").write_text("20180503,1,0.2,0\n20501231,1,1,0\n")
        (krx / "securities.csv").write_text("code,name,market\nA00001,TEST STOCK,KOSPI\n")
        self.code = root / "code"
        self.code.mkdir()
        (self.code / "main.py").write_text('self.set_benchmark(krx_benchmark("A00001"))\n')

    def tearDown(self):
        self.tmp.cleanup()

    def bench(self, values, first="20180501"):
        return [[ts(first), values[0]]] + [[ts(d), v] for d, v in zip(DAYS, values)]   # a sample before the data too

    def test_index_found_from_its_values(self):
        self.assertEqual(results.benchmark_name(self.ws, self.code, {}, self.bench([330.0, 330.0, 331.0, 332.0, 333.0])), "KOSPI 200")
        self.assertEqual(results.benchmark_name(self.ws, self.code, {}, self.bench([870.0, 870.0, 860.0, 880.0, 890.0])), "KOSDAQ")

    def test_stock_from_the_code_adjusted(self):
        adjusted = [100_000.0, 100_000.0, 102_000.0, 102_000.0, 103_000.0]          # no jump across the split
        self.assertEqual(results.benchmark_name(self.ws, self.code, {}, self.bench(adjusted)), "A00001 TEST STOCK")
        (self.code / "main.py").write_text("")                                       # code not named anywhere: not tried
        self.assertEqual(results.benchmark_name(self.ws, self.code, {}, self.bench(adjusted)), "")
        self.assertEqual(results.benchmark_name(self.ws, self.code, {"bench": "A00001"}, self.bench(adjusted)),
                         "A00001 TEST STOCK")                                         # ... or in the parameters

    def test_nothing_matches(self):
        self.assertEqual(results.benchmark_name(self.ws, self.code, {}, self.bench([1.0, 2.0, 3.0, 4.0, 5.0])), "")
        self.assertEqual(results.benchmark_name(self.ws, self.code, {}, []), "")

    def test_max_drawdown(self):
        dd = [[1, 0.0], [2, -5.0], [3, -12.5], [4, -3.0], [5, 0.0], [6, -8.0]]
        self.assertEqual(gui.max_drawdown(dd), {"value": -12.5, "time": 3, "peak": 1, "recovered": 5})
        self.assertEqual(gui.max_drawdown([[1, 0.0], [2, -4.0], [3, -9.0]])["recovered"], None)   # never got back
        self.assertEqual(gui.max_drawdown([[1, 0.0], [2, 0.0]]), {"value": 0.0, "time": None, "peak": None, "recovered": None})
        self.assertIsNone(gui.max_drawdown([]))


if __name__ == "__main__":
    unittest.main()
