import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parent), str(_HERE.parents[2])]   # tests/klean (helpers) and the repo root

from klean import research, results
from klean.workspace import KleanError, Workspace


class ResearchTest(unittest.TestCase):
    """What `klean research` writes; Jupyter itself is tested by running a notebook on a LEAN build."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        lean = root / "Lean"
        self.bin = lean / "Launcher" / "bin" / "Release"
        self.bin.mkdir(parents=True)
        (self.bin / "start.py").write_text("# LEAN's start.py\n")
        (self.bin / "QuantConnect.Research.dll").write_bytes(b"")
        venv = root / "py311"
        (venv / "lib" / "python3.11" / "site-packages").mkdir(parents=True)
        (root / "libpython3.11.so").write_bytes(b"")
        self.ws = Workspace(root=root / "ws", lean_root=str(lean), python_venv=str(venv),
                            python_dll=str(root / "libpython3.11.so"), lean_config={"maximum-data-points-per-chart-series": "4000"})
        self.ws.data.mkdir(parents=True)
        self.project = self.ws.root / "P"
        self.project.mkdir()
        def python_env(ws):        # the real one asks the venv's python for its site-packages
            if not ws.python_venv:
                raise KleanError("no Python environment")
            return {"PYTHONNET_PYDLL": ws.python_dll, "PYTHONPATH": "site-packages"}
        self.patches = [mock.patch.object(research, "dotnet", lambda: str(root / "dotnet" / "dotnet")),
                        mock.patch.object(research, "python_env", python_env)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_prepare_writes_config_and_startup(self):
        env = research.prepare(self.ws)
        folder = research.research_dir(self.ws)
        config = json.loads((folder / "config.json").read_text())
        self.assertEqual(config["data-folder"], f"{self.ws.data}/")
        self.assertEqual(config["composer-dll-directory"], f"{self.bin}/")
        self.assertEqual(config["object-store-root"], str(self.ws.root / "storage"))
        self.assertEqual(config["log-handler"], "QuantConnect.Logging.FileLogHandler")
        self.assertEqual(config["maximum-data-points-per-chart-series"], "4000")   # workspace LEAN keys
        startup = (folder / "ipython" / "profile_default" / "startup" / research.STARTUP).read_text()
        compile(startup, "startup", "exec")                                   # valid Python
        self.assertIn(repr(str(self.bin / "start.py")), startup)
        self.assertIn("Config.SetConfigurationFile(" + repr(str(folder / "config.json")), startup)
        self.assertTrue((folder / "lib" / "krx_models.py").exists())
        self.assertEqual(env["IPYTHONDIR"], str(folder / "ipython"))
        self.assertEqual(env["DOTNET_ROOT"], str(Path(self.tmp.name).resolve() / "dotnet"))
        self.assertEqual(env["PYTHONNET_PYDLL"], self.ws.python_dll)
        self.assertNotIn("SYNTHETIC", startup)

    def test_demo_banner_and_template(self):
        (self.ws.data / "equity" / "krx").mkdir(parents=True)
        (self.ws.data / "equity" / "krx" / results.DEMO_MARKER).write_text("synthetic")
        research.prepare(self.ws)
        startup = (research.research_dir(self.ws) / "ipython" / "profile_default" / "startup" / research.STARTUP)
        self.assertIn("SYNTHETIC DEMO DATA", startup.read_text())
        nb = json.loads(research.ensure_notebook(self.ws, self.project).read_text())
        text = json.dumps(nb)
        self.assertIn("D00010", text)
        self.assertIn("SYNTHETIC DEMO DATA", text)
        self.assertEqual(nb["nbformat"], 4)
        for cell in nb["cells"]:
            if cell["cell_type"] == "code":
                compile(cell["source"], "cell", "exec")

    def test_existing_notebook_is_kept(self):
        nb = self.project / research.NOTEBOOK
        nb.write_text('{"mine": true}')
        research.ensure_notebook(self.ws, self.project)
        self.assertEqual(nb.read_text(), '{"mine": true}')
        real = research.notebook_template(demo=False)
        self.assertIn("005930", json.dumps(real))

    def test_needs_lean_research_files_and_python(self):
        (self.bin / "QuantConnect.Research.dll").unlink()
        with self.assertRaises(KleanError):
            research.prepare(self.ws)
        self.ws.python_venv = ""
        with self.assertRaises(KleanError):
            research.prepare(self.ws)


if __name__ == "__main__":
    unittest.main()
