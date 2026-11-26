"""krx_benchmark for stocks (examples/python/krx_models.py): daily closes adjusted with the factor
file as LEAN adjusts prices. krx_models.py imports LEAN, so the functions are taken from its
source. (C# KrxIndex.LoadStockDaily gives the same numbers: checked against LEAN's own adjusted
prices in a backtest, 118 days across a split and dividends.)"""
import ast
import bisect
import os
import tempfile
import unittest
import zipfile
from datetime import date, datetime
from pathlib import Path

_HERE = Path(__file__).resolve()
MODELS = _HERE.parents[2] / "examples" / "python" / "krx_models.py"


def functions(*names: str, data_folder: str) -> dict:
    tree = ast.parse(MODELS.read_text(encoding="utf-8"))
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = {"bisect": bisect, "os": os, "zipfile": zipfile, "datetime": datetime, "_data_folder": lambda: data_folder}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(MODELS), "exec"), ns)
    return ns


class StockBenchmarkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        krx = self.data / "equity" / "krx"
        (krx / "daily").mkdir(parents=True)
        (krx / "factor_files").mkdir()
        bars = {"20180502": 500_000, "20180503": 500_000, "20180504": 100_000, "20181227": 120_000, "20181228": 110_000}
        with zipfile.ZipFile(krx / "daily" / "a00001.zip", "w") as z:
            z.writestr("a00001.csv", "".join(f"{d} 00:00,0,0,0,{c * 10000},1\n" for d, c in bars.items()))
        # a 5:1 split after 2018-05-03, a dividend after 2018-12-27 (factor 0.98), as krx-lean writes them
        (krx / "factor_files" / "a00001.csv").write_text(
            "20180502,0.98,0.2,0\n20180503,0.98,0.2,500000\n20181227,0.98,1,120000\n20501231,1,1,0\n")
        with zipfile.ZipFile(krx / "daily" / "b00002.zip", "w") as z:          # no factor file: unadjusted
            z.writestr("b00002.csv", "20180502 00:00,0,0,0,70000000,1\n")
        (self.data / "index" / "krx" / "daily").mkdir(parents=True)
        with zipfile.ZipFile(self.data / "index" / "krx" / "daily" / "kospi200.zip", "w") as z:
            z.writestr("kospi200.csv", "20180502 00:00,1,1,1,330.5,0\n")
        self.ns = functions("load_index", "load_stock", "krx_benchmark", data_folder=str(self.data))

    def tearDown(self):
        self.tmp.cleanup()

    def test_adjusted_like_lean(self):
        dates, closes = self.ns["load_stock"]("A00001")
        self.assertEqual(dates[0], date(2018, 5, 2))
        # LEAN: the factor of the first row dated on or after the day
        expected = [500_000 * 0.98 * 0.2, 500_000 * 0.98 * 0.2, 100_000 * 0.98, 120_000 * 0.98, 110_000]
        for got, want in zip(closes, expected):
            self.assertAlmostEqual(got, want, places=6)
        # no jump across the split: 98,000 -> 98,000
        self.assertAlmostEqual(closes[1], closes[2], places=6)

    def test_benchmark_function(self):
        bench = self.ns["krx_benchmark"]("A00001")
        self.assertAlmostEqual(bench(datetime(2018, 5, 4, 15, 30)), 98_000, places=6)
        self.assertAlmostEqual(bench(datetime(2018, 5, 10)), 98_000, places=6)      # last close on or before
        self.assertAlmostEqual(bench(datetime(2019, 1, 2)), 110_000, places=6)
        self.assertAlmostEqual(self.ns["krx_benchmark"]("b00002")(datetime(2018, 5, 2)), 7_000, places=6)
        self.assertEqual(self.ns["krx_benchmark"]("kospi200")(datetime(2018, 5, 2)), 330.5)       # indices first
        with self.assertRaisesRegex(FileNotFoundError, "no NOPE index data"):
            self.ns["krx_benchmark"]("NOPE")                        # a name: an index
        with self.assertRaisesRegex(FileNotFoundError, "no KRX index or stock 005930: neither .*index.* nor .*equity"):
            self.ns["krx_benchmark"]("005930")                      # a code: say both
        with self.assertRaisesRegex(FileNotFoundError, "no KRX index or stock 0041B0"):
            self.ns["krx_benchmark"]("0041B0")                      # newer codes have letters


if __name__ == "__main__":
    unittest.main()
