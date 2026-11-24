"""One JupyterLab layout per project, kept in <project>/.jupyter/layout.json (klean.research),
against a fake JupyterLab with the workspaces and sessions APIs."""
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parent), str(_HERE.parents[2])]

from klean import gui, projects, research
from klean.workspace import Workspace


class FakeLab:
    """The JupyterLab server APIs klean uses: /lab/api/workspaces/<id> (GET, PUT), /api/sessions
    (GET), /api/sessions/<id> (DELETE)."""

    def __init__(self):
        self.spaces, self.sessions, self.calls = {}, [], []
        lab = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj, status=200):
                body = json.dumps(obj).encode() if obj is not None else b""
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                lab.calls.append(("GET", self.path, self.headers["Authorization"]))
                if self.path.startswith("/lab/api/workspaces/"):
                    return self._send(lab.spaces.get(self.path.rsplit("/", 1)[1], {"data": {}, "metadata": {}}))
                if self.path == "/api/sessions":
                    return self._send(lab.sessions)
                self._send({}, 404)

            def do_PUT(self):  # noqa: N802
                lab.calls.append(("PUT", self.path, self.headers["Authorization"]))
                lab.spaces[self.path.rsplit("/", 1)[1]] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self._send(None, 204)

            def do_DELETE(self):  # noqa: N802
                lab.calls.append(("DELETE", self.path, self.headers["Authorization"]))
                lab.sessions = [s for s in lab.sessions if s["id"] != self.path.rsplit("/", 1)[1]]
                self._send(None, 204)

        self.server = gui.LocalServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def dock(space: dict) -> dict:
    return space["data"]["layout-restorer:data"]["main"]["dock"]


class LayoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        lean = base / "Lean"
        (lean / "Launcher" / "bin" / "Release").mkdir(parents=True)
        self.root = base / "ws"
        (self.root / "data").mkdir(parents=True)
        self.ws = Workspace(root=self.root, lean_root=str(lean))
        self.ws.save()
        self.project = projects.create(self.ws, "Top 20", "python", "empty")
        self.lab = FakeLab()

    def tearDown(self):
        self.lab.close()
        self.tmp.cleanup()

    def test_first_open_is_the_strategy_and_notebook_side_by_side(self):
        url = research.open_layout(self.lab.port, "tok", "Top 20", self.project)
        self.assertEqual(url, f"http://127.0.0.1:{self.lab.port}/lab/workspaces/klean-p-Top-20?token=tok")
        self.assertEqual(self.lab.calls[0][1:], ("/lab/api/workspaces/klean-p-Top-20", "token tok"))
        space = self.lab.spaces["klean-p-Top-20"]
        self.assertEqual([c["widgets"] for c in dock(space)["children"]],
                         [["editor:Top 20/main.py"], ["notebook:Top 20/research.ipynb"]])
        self.assertEqual(space["data"]["notebook:Top 20/research.ipynb"]["data"]["path"], "Top 20/research.ipynb")
        self.assertEqual(space["data"]["file-browser-filebrowser:cwd"]["path"], "Top 20")
        self.assertEqual(research.space_id(""), "klean-solo")          # `klean research P`: the project is the root

    def test_saved_in_the_project_relative_and_restored_after_a_rename(self):
        research.open_layout(self.lab.port, "tok", "Top 20", self.project)
        # the user opens a third file and a file of another project in JupyterLab
        (self.project / "util.py").write_text("x = 1\n")
        space = self.lab.spaces["klean-p-Top-20"]
        space["data"]["editor:Top 20/util.py"] = {"data": {"path": "Top 20/util.py", "factory": "Editor"}}
        space["data"]["editor:Other/x.py"] = {"data": {"path": "Other/x.py", "factory": "Editor"}}
        dock(space)["children"][0]["widgets"] += ["editor:Top 20/util.py", "editor:Other/x.py"]
        self.assertTrue(research.save_layout(self.lab.port, "tok", "Top 20", self.project))
        saved = json.loads(research.layout_path(self.project).read_text())
        self.assertEqual([c["widgets"] for c in dock({"data": saved})["children"]],
                         [["editor:main.py", "editor:util.py"], ["notebook:research.ipynb"]])   # Other/x.py left out
        self.assertNotIn("editor:Other/x.py", saved)
        self.assertEqual(saved["file-browser-filebrowser:cwd"]["path"], "")
        self.assertEqual((self.project / ".jupyter" / ".gitignore").read_text().splitlines()[-1], "*")
        self.assertFalse(research.save_layout(self.lab.port, "tok", "Top 20", self.project))   # unchanged: not rewritten
        # renamed project: the same tabs under the new name
        renamed = self.project.rename(self.root / "Renamed")
        research.open_layout(self.lab.port, "tok", "Renamed", renamed)
        self.assertEqual([c["widgets"] for c in dock(self.lab.spaces["klean-p-Renamed"])["children"]],
                         [["editor:Renamed/main.py", "editor:Renamed/util.py"], ["notebook:Renamed/research.ipynb"]])

    def test_deleted_files_and_reset(self):
        research.open_layout(self.lab.port, "tok", "Top 20", self.project)
        research.save_layout(self.lab.port, "tok", "Top 20", self.project)
        (self.project / "research.ipynb").unlink()            # gone: its tab is left out, its area too
        research.open_layout(self.lab.port, "tok", "Top 20", self.project)
        self.assertEqual(dock(self.lab.spaces["klean-p-Top-20"]), {"type": "tab-area", "currentIndex": 0,
                                                                   "widgets": ["editor:Top 20/main.py"]})
        (self.project / "main.py").unlink()                   # nothing left to show: the default layout
        research.ensure_notebook(self.ws, self.project)
        (self.project / "main.py").write_text("x = 1\n")
        research.layout_path(self.project).write_text("not json")
        research.open_layout(self.lab.port, "tok", "Top 20", self.project)
        self.assertEqual(len(dock(self.lab.spaces["klean-p-Top-20"])["children"]), 2)
        research.open_layout(self.lab.port, "tok", "Top 20", self.project, reset=True)    # reset also saves
        self.assertIn('"notebook:research.ipynb"', research.layout_path(self.project).read_text())

    def test_project_kernels(self):
        self.lab.sessions = [{"id": "a", "path": "Top 20/research.ipynb"}, {"id": "b", "path": "Top 20/x/n.ipynb"},
                             {"id": "c", "path": "Other/research.ipynb"}, {"id": "d", "path": "Top 2/research.ipynb"}]
        self.assertEqual([s["id"] for s in research.project_kernels(self.lab.port, "tok", "Top 20")], ["a", "b"])
        self.assertEqual(research.shutdown_kernels(self.lab.port, "tok", "Top 20"), 2)
        self.assertEqual([s["id"] for s in self.lab.sessions], ["c", "d"])

    def test_hidden_from_snapshots_and_the_project_page(self):
        research.open_layout(self.lab.port, "tok", "Top 20", self.project)
        research.save_layout(self.lab.port, "tok", "Top 20", self.project)
        from klean import results
        self.assertNotIn(".jupyter/layout.json", [p.relative_to(self.project).as_posix()
                                                  for p in results.source_files(self.project)])
        self.assertNotIn(".jupyter/layout.json", gui.api_project(self.ws, {"name": ["Top 20"]})["files"])

    def test_jupyter_settings(self):
        cmd = research.jupyter_command(self.ws, self.root, 1, "t")
        self.assertIn(f"--LabApp.workspaces_dir={self.root / '.klean' / 'research' / 'lab-workspaces'}", cmd)
        self.assertIn("--MappingKernelManager.cull_idle_timeout=3600", cmd)
        self.assertIn("--MappingKernelManager.cull_connected=False", cmd)


if __name__ == "__main__":
    unittest.main()
