"""Parameters found in a strategy's code (klean.params), for the GUI's backtest and optimization forms."""
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parent), str(_HERE.parents[2])]

from klean import params, projects
from klean.workspace import REPO_ROOT, Workspace


def table(found):
    return [(e["name"], e["default"], e["kind"]) for e in found]


class ParamsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_python(self):
        self.write("main.py", '''
LOOKBACK = 60
class A(QCAlgorithm):
    HOLDINGS = 20
    WEIGHT: float = 0.5
    def initialize(self):
        set_period(self, "2015-01-02")
        self.n = int(self.get_parameter("holdings", str(self.HOLDINGS)))
        self.w = float(self.get_parameter("weight", str(A.WEIGHT)))
        self.lb = self.get_parameter("lookback", LOOKBACK)
        self.m = self.get_parameter("market", "KOSPI").upper()
        self.t = self.get_parameter("threshold", default_value=-1.5)
        self.x = self.get_parameter("computed", str(len("abc")))
        self.y = self.get_parameter("bare")
        self.z = self.get_parameter(name_variable, "1")         # not a literal name: skipped
        self.n2 = int(self.get_parameter("holdings", "99"))     # the first place counts
''')
        self.write("krx_models.py", 'def set_period(a, s, e=None):\n    a.get_parameter("start_date")\n')
        self.write("lib/signals.py", 'def f(algo):\n    return algo.GetParameter("fast", 5)\n')
        found = params.find(self.dir)
        self.assertEqual(table(found), [
            ("start_date", "2015-01-02", "date"), ("end_date", "", "date"), ("holdings", "20", "int"),
            ("weight", "0.5", "float"), ("lookback", "60", "int"), ("market", "KOSPI", "text"),
            ("threshold", "-1.5", "float"), ("computed", "", "text"), ("bare", "", "text"), ("fast", "5", "int")])
        self.assertEqual(found[2]["where"], "main.py:8")
        self.assertEqual(found[-1]["where"], "lib/signals.py:2")
        self.write("main.py", "def broken(:\n")                    # a syntax error: nothing, no crash
        self.assertEqual(table(params.find(self.dir)), [("fast", "5", "int")])

    def test_csharp(self):
        self.write("Main.cs", '''
public class A : QCAlgorithm {
    private const int Holdings = 20;
    private static readonly decimal Weight = 0.9m;
    public override void Initialize() {
        KrxModels.SetPeriod(this, "2015-01-02", "2025-12-30");
        _n = GetParameter("holdings", Holdings);
        _w = GetParameter("weight", Weight);
        _r = GetParameter("ratio", 1.25m);
        _m = GetParameter("market", "KOSPI").ToUpperInvariant();
        _s = GetParameter("slippage_ticks", 0);
        _b = GetParameter("bare");
        // _old = GetParameter("commented", 1);
    }
}''')
        self.write("KrxModels.cs", 'var s = algorithm.GetParameter("start_date");')
        self.assertEqual(table(params.find(self.dir)), [
            ("start_date", "2015-01-02", "date"), ("end_date", "2025-12-30", "date"), ("holdings", "20", "int"),
            ("weight", "0.9", "float"), ("ratio", "1.25", "float"), ("market", "KOSPI", "text"),
            ("slippage_ticks", "0", "int"), ("bare", "", "text")])

    def test_templates_and_examples(self):
        lean = self.dir / "Lean"
        (lean / "Launcher" / "bin" / "Release").mkdir(parents=True)
        ws = Workspace(root=self.dir / "ws", lean_root=str(lean))
        (ws.root / "data").mkdir(parents=True)
        ws.save()
        expected = [("start_date", "2011-01-01", "date"), ("end_date", "2026-09-30", "date"), ("holdings", "20", "int"),
                    ("market", "KOSPI", "text"), ("slippage_ticks", "0", "int")]
        for lang in ("python", "csharp"):
            p = projects.create(ws, f"top-{lang}", lang, "top-market-cap")
            self.assertEqual(table(params.find(p)), expected, lang)
            p = projects.create(ws, f"hold-{lang}", lang, "buy-hold")
            self.assertEqual(table(params.find(p)), [("start_date", "2024-01-02", "date"), ("end_date", "", "date"),
                                                     ("slippage_ticks", "0", "int"), ("code", "005930", "text")], lang)
        self.assertTrue((REPO_ROOT / "examples" / "python" / "krx_top_market_cap" / "main.py").exists())


if __name__ == "__main__":
    unittest.main()
