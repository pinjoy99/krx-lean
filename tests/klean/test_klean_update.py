import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parent), str(_HERE.parents[2])]   # tests/klean (helpers) and the repo root

from klean import cli, projects, results
from klean.workspace import KleanError, Workspace
from krx_lean import build, demo


def quiet(func, *args):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        code = func(*args)
    return code, out.getvalue()


class ModelsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(root=Path(self.tmp.name) / "ws", lean_root=str(Path(self.tmp.name) / "Lean"))
        self.ws.data.mkdir(parents=True)
        self.py = projects.create(self.ws, "P", "python", "empty")
        self.cs = projects.create(self.ws, "C", "csharp", "empty")

    def tearDown(self):
        self.tmp.cleanup()

    def test_state_update_and_doctor_row(self):
        self.assertEqual([p.name for p in projects.list_projects(self.ws)], ["C", "P"])
        self.assertEqual((projects.models_state(self.py), projects.models_state(self.cs)), ("current", "current"))
        self.assertEqual(projects.models_row(self.ws), ("KRX models in projects", True, "all current"))
        copy = self.py / "krx_models.py"
        copy.write_text(copy.read_text() + "\n# an older version\n")
        self.assertEqual(projects.models_state(self.py), "differs")
        item, ok, detail = projects.models_row(self.ws)
        self.assertTrue(ok)                                   # informational: never fails doctor
        self.assertIn("note: P differ", detail)
        backup = projects.update_models(self.py)
        self.assertEqual(backup.name, "krx_models.py.bak")
        self.assertIn("# an older version", backup.read_text())
        self.assertEqual(projects.models_state(self.py), "current")
        self.assertIsNone(projects.update_models(self.py))    # already current: nothing to do
        (self.cs / "KrxModels.cs").unlink()
        self.assertEqual(projects.models_state(self.cs), "missing")
        self.assertIsNone(projects.update_models(self.cs))
        self.assertEqual(projects.models_state(self.cs), "current")

    def test_templates_use_the_shared_initializer_and_slippage_parameter(self):
        self.assertIn('krx_initialize(security, boards, slippage_ticks=slippage_ticks)', (self.py / "main.py").read_text())
        self.assertIn('KrxModels.Initialize(security, boards, slippageTicks: slippageTicks)', (self.cs / "Main.cs").read_text())
        self.assertIn("class KrxSlippageModel", projects.PY_MODELS.read_text())
        self.assertIn("class KrxSlippageModel : ISlippageModel", projects.CS_MODELS.read_text())


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data_root = root / "krx-data"            # a built data root that isn't marked as demo data
        demo.generate(self.data_root, start="20240102", end="20240131")
        (self.data_root / demo.MARKER).unlink()
        with self.assertLogs(level="INFO"):
            build.build(self.data_root)
        self.ws = Workspace(root=root / "ws", lean_root=str(root / "Lean"))
        (self.ws.data / "market-hours").mkdir(parents=True)
        (self.ws.data / "market-hours" / "market-hours-database.json").write_text(
            '{"entries": {"Index-krx-[*]": {"holidays": []}}}')
        (self.ws.data / "symbol-properties").mkdir()
        (self.ws.data / "symbol-properties" / "symbol-properties-database.csv").write_text("market,symbol\n")
        self.ws.save()
        self.cwd = os.getcwd()
        os.chdir(self.ws.root)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def args(self, **kw):
        return type("Args", (), {"root": None, "env_file": str(Path(self.tmp.name) / "none.env"), **kw})()

    def test_update_remembers_the_root_and_installs(self):
        with self.assertRaises(KleanError):                    # no root known yet
            cli.cmd_update(self.args())
        calls = []
        with mock.patch("krx_lean.cli.main", lambda argv: calls.append(argv) or 0), self.assertLogs(level="INFO"):
            code, out = quiet(cli.cmd_update, self.args(root=str(self.data_root)))
        self.assertEqual(code, 0)
        self.assertEqual(calls, [["--root", str(self.data_root), "all"]])
        self.assertIn("20240102 → 20240131", out)
        self.assertEqual(Workspace.load(self.ws.root).data_root, str(self.data_root.resolve()))
        with mock.patch("krx_lean.cli.main", lambda argv: calls.append(argv) or 1), self.assertLogs(level="INFO"):
            code, out = quiet(cli.cmd_update, self.args())     # root remembered; download stopped early
        self.assertEqual(code, 1)
        self.assertIn("run `klean update` again", out)

    def test_update_refuses_demo_workspaces_and_explains_missing_keys(self):
        with mock.patch("krx_lean.cli.main", side_effect=SystemExit("KRX_API_KEY is not set")):
            with self.assertRaises(KleanError) as e:
                quiet(cli.cmd_update, self.args(root=str(self.data_root)))
        self.assertIn("KRX_API_KEY is not set", str(e.exception))
        (self.ws.data / "equity" / "krx").mkdir(parents=True, exist_ok=True)
        (self.ws.data / "equity" / "krx" / results.DEMO_MARKER).write_text("synthetic")
        with self.assertRaises(KleanError):
            cli.cmd_update(self.args(root=str(self.data_root)))

    def test_env_file(self):
        env = Path(self.tmp.name) / "keys.env"
        env.write_text("# keys\nKLEAN_TEST_A=abc\nexport KLEAN_TEST_B='quoted value'\nKLEAN_TEST_C=\nnot a line\n")
        with mock.patch.dict(os.environ, {"KLEAN_TEST_A": "already set"}):
            names = cli.load_env_file(env)
            self.assertEqual(names, ["KLEAN_TEST_B"])
            self.assertEqual(os.environ["KLEAN_TEST_A"], "already set")
            self.assertEqual(os.environ["KLEAN_TEST_B"], "quoted value")
            self.assertNotIn("KLEAN_TEST_C", os.environ)


if __name__ == "__main__":
    unittest.main()
