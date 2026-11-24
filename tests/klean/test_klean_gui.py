import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parent), str(_HERE.parents[2])]   # tests/klean (helpers) and the repo root

from klean import gui, results, projects
from klean.workspace import Workspace
from test_klean_p1 import make_run


class GuiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        lean = base / "Lean"
        (lean / "Launcher" / "bin" / "Release").mkdir(parents=True)
        (lean / "Data" / "market-hours").mkdir(parents=True)
        self.root = base / "ws"
        (self.root / "data").mkdir(parents=True)
        self.ws = Workspace(root=self.root, lean_root=str(lean))
        self.ws.save()
        projects.create(self.ws, "A", "python")
        stats = {"Total Orders": "1", "End Equity": "110", "Compounding Annual Return": "5%"}
        make_run(self.root / "A", "2026-10-28_10-00-00", 110.0, stats)
        make_run(self.root / "A", "2026-10-28_11-00-00", 110.0, stats)
        self.outside = make_run(base / "other", "2026-10-28_10-00-00", 1.0, stats)
        self.token = "t0ken"
        self.server = gui.LocalServer(("127.0.0.1", 0), gui.make_handler(self.ws, self.token, gui.Jobs()))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def get(self, path, token=True, data=None, header=True):
        req = urllib.request.Request(self.base + path, data=data)
        if token and header:
            req.add_header("X-Klean-Token", self.token)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_token_required(self):
        self.assertEqual(self.get("/", token=False)[0], 403)
        self.assertEqual(self.get("/api/workspace?token=wrong", token=False)[0], 403)
        status, body = self.get(f"/?token={self.token}", token=False)
        self.assertEqual(status, 200)
        self.assertIn(b"<title>klean</title>", body)
        # POST needs the header (a cross-site form can't set it), the query token isn't enough
        self.assertEqual(self.get(f"/api/backtest?token={self.token}", header=False, data=b"{}")[0], 403)

    def test_api(self):
        w = json.loads(self.get("/api/workspace")[1])
        self.assertEqual([(p["name"], p["runs"]) for p in w["projects"]], [("A", 2)])
        p = json.loads(self.get("/api/project?name=A")[1])
        self.assertEqual([r["name"] for r in p["runs"]], ["2026-10-28_11-00-00", "2026-10-28_10-00-00"])
        r = json.loads(self.get("/api/run?ref=A")[1])
        self.assertEqual(r["ref"], "A/backtests/2026-10-28_11-00-00")
        self.assertEqual(r["equity"][-1], [1700086400, 110.0])
        c = json.loads(self.get("/api/compare?ref=A/2026-10-28_10&ref=A/2026-10-28_11")[1])
        self.assertTrue(c["verdict"]["identical"])
        self.assertEqual(json.loads(self.get("/api/log?ref=A&tail=1")[1])["lines"], ["line 3"])

    def test_create_project(self):
        def post(body):
            return self.get("/api/create-project", data=json.dumps(body).encode())
        status, body = post({"name": "Momentum", "language": "python", "template": "empty"})
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body), {"name": "Momentum", "language": "python", "template": "empty",
                                            "files": ["main.py", "research.ipynb"]})
        self.assertTrue((self.root / "Momentum" / "research.ipynb").exists())
        w = json.loads(self.get("/api/workspace")[1])
        self.assertIn("Momentum", [p["name"] for p in w["projects"]])
        status, body = post({"name": "CsOne", "language": "csharp"})
        self.assertEqual(json.loads(body)["files"], ["Main.cs", "research.ipynb"])
        for bad, why in (({"name": "A"}, b"already exists"), ({"name": ""}, b"name"), ({"name": "x/y"}, b"one folder"),
                         ({"name": ".."}, b"valid"), ({"name": "Q", "template": "nope"}, b"unknown template"),
                         ({"name": "Q", "language": "go"}, b"unknown language")):
            status, body = post(bad)
            self.assertEqual(status, 400, bad)
            self.assertIn(why, body, bad)
        self.assertFalse((self.root / "Q").exists())

    def test_static_files(self):
        # the page's code and styles load without the token (they hold no data)...
        for path in ("/static/js/main.js", "/static/js/pages/run.js", "/static/app.css",
                     "/static/vendor/uplot/uPlot.esm.js"):
            self.assertEqual(self.get(path, token=False)[0], 200, path)
        # ...but nothing outside klean/static, and only scripts and styles
        for path in ("/static/../gui.py", "/static/%2e%2e/gui.py", "/static/index.html",
                     "/static/vendor/uplot/LICENSE", "/static/nope.js"):
            self.assertEqual(self.get(path, token=False)[0], 404, path)
        self.assertIsNone(gui.static_file("/static/../../klean.json"))
        # every module the page imports exists (a missing one would leave the page blank)
        import re
        for js in gui.STATIC.rglob("*.js"):
            if "vendor" in js.parts:
                continue
            for target in re.findall(r'from "(\.{1,2}/[^"]+)"', js.read_text()):
                self.assertTrue((js.parent / target).resolve().is_file(), f"{js.name} imports {target}")

    def test_page_security_headers(self):
        req = urllib.request.Request(f"{self.base}/?token={self.token}")
        with urllib.request.urlopen(req) as r:
            csp = r.headers["Content-Security-Policy"]
        self.assertIn("script-src 'self'", csp)          # no inline or third-party scripts
        self.assertIn("frame-ancestors 'none'", csp)     # can't be framed by another site
        self.assertNotIn("<script>", (gui.STATIC / "index.html").read_text())

    def test_server_starts_without_a_dns_lookup(self):
        # HTTPServer.server_bind calls socket.getfqdn, which hung for minutes on macOS CI
        from unittest import mock
        with mock.patch("socket.getfqdn", side_effect=AssertionError("reverse DNS lookup")):
            server = gui.LocalServer(("127.0.0.1", 0), gui.make_handler(self.ws, "t", gui.Jobs()))
        self.assertEqual(server.server_name, "127.0.0.1")
        server.server_close()

    def test_research_endpoint(self):
        import json
        # GET only reports; nothing is started
        status, body = self.get("/api/research")
        self.assertEqual((status, json.loads(body)), (200, {"status": "off"}))
        # POST for a project outside the workspace is refused before anything starts
        status, body = self.get("/api/research", data=json.dumps({"project": "../x"}).encode())
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(self.get("/api/research")[1])["status"], "off")
        # the page may frame JupyterLab (another port on 127.0.0.1), nothing else
        self.assertIn("frame-src 'self' http://127.0.0.1:*;", gui.PAGE_CSP)

    def test_jupyter_may_be_framed_by_the_gui_only(self):
        from klean import research
        cmd = research.jupyter_command(self.ws, self.ws.root, 8888, "tok", "http://127.0.0.1:5000")
        setting = next(c for c in cmd if c.startswith("--ServerApp.tornado_settings="))
        self.assertIn("frame-ancestors 'self' http://127.0.0.1:5000", setting)
        self.assertIn("--ip=127.0.0.1", cmd)
        plain = research.jupyter_command(self.ws, self.ws.root, 8888, "tok")
        self.assertFalse(any(c.startswith("--ServerApp.tornado_settings") for c in plain))

    def test_outside_workspace_refused(self):
        status, body = self.get("/api/run?ref=" + urllib.request.quote(str(self.outside)))
        self.assertEqual(status, 400)
        self.assertIn(b"outside the workspace", body)
        status, _ = self.get("/api/backtest", data=json.dumps({"project": "../other"}).encode())
        self.assertEqual(status, 400)

    def test_optimization_api(self):
        opt = self.root / "A" / "optimizations" / "o1"
        stats = {"Sharpe Ratio": "0.2", "End Equity": "110", "Drawdown": "10%"}
        opt.mkdir(parents=True)
        for i, (h, sh) in enumerate([("5", "0.1"), ("10", "0.3")], 1):
            run = opt / f"{i:03d}_h={h}"
            run.mkdir()
            (run / "Algo-summary.json").write_text(json.dumps({"statistics": {**stats, "Sharpe Ratio": sh}}))
        runs = [{"index": i, "folder": f"{i:03d}_h={h}", "parameters": {"h": h}, "ok": True, "passes": True,
                 "target_value": float(sh), "failed_constraints": [], "stats": {"Sharpe Ratio": sh}}
                for i, (h, sh) in enumerate([("5", "0.1"), ("10", "0.3")], 1)]
        (opt / "optimization.json").write_text(json.dumps({
            "project": "A", "algorithm": "A", "language": "python", "strategy": "grid", "target": "Sharpe Ratio",
            "direction": "max", "constraints": [], "parameters": [{"name": "h", "min": "5", "max": "10", "step": "5"}],
            "lean_config": {}, "started_utc": "", "seconds": 1, "concurrent": 2, "runs": runs, "best": "002_h=10"}))
        p = json.loads(self.get("/api/project?name=A")[1])
        self.assertEqual(p["optimizations"][0]["best"]["parameters"], {"h": "10"})
        self.assertNotIn("optimizations/o1/optimization.json", p["files"])
        o = json.loads(self.get("/api/optimization?project=A&name=o1")[1])
        self.assertEqual(o["row_refs"], ["A/optimizations/o1/002_h=10", "A/optimizations/o1/001_h=5"])
        r = json.loads(self.get("/api/run?ref=" + urllib.request.quote("A/optimizations/o1/002_h=10"))[1])
        self.assertEqual(r["statistics"]["Sharpe Ratio"], "0.3")
        self.assertEqual(self.get("/api/optimization?project=A&name=..")[0], 400)

    def test_code_snapshot(self):
        run = self.root / "A" / "backtests" / "2026-10-28_11-00-00"
        ref = urllib.request.quote("A/backtests/2026-10-28_11-00-00")
        (run / "code" / "lib").mkdir(parents=True)
        (run / "code" / "main.py").write_text("print(1)")
        (run / "code" / "lib" / "u.py").write_text("u")
        self.assertEqual(json.loads(self.get("/api/run?ref=" + ref)[1])["code"], ["lib/u.py", "main.py"])
        f = json.loads(self.get(f"/api/code-file?ref={ref}&path=main.py")[1])
        self.assertEqual(f["text"], "print(1)")
        self.assertEqual(self.get(f"/api/code-file?ref={ref}&path=..%2Fconsole.txt")[0], 400)
        self.assertEqual(self.get(f"/api/code-file?ref={ref}&path=%2Fetc%2Fpasswd")[0], 400)

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(),
                                     headers={"X-Klean-Token": self.token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_rename_and_delete_runs(self):
        run = make_run(self.root / "A", "2026-11-01_09-00-00_old", 100.0, {"End Equity": "1"})
        status, body = self.post("/api/run-rename", {"ref": "A/backtests/2026-11-01_09-00-00_old", "name": "new name!"})
        self.assertEqual((status, body["ref"]), (200, "A/backtests/2026-11-01_09-00-00_new-name"))
        self.assertFalse(run.exists())
        renamed = self.root / "A" / "backtests" / "2026-11-01_09-00-00_new-name"
        self.assertTrue(renamed.is_dir())
        # only run folders directly in a project's backtests/ can be touched
        for ref in ("A", "A/backtests", "data", "../x", "A/backtests/../../data"):
            self.assertEqual(self.post("/api/run-delete", {"ref": ref})[0], 400, ref)
            self.assertEqual(self.post("/api/run-rename", {"ref": ref, "name": "x"})[0], 400, ref)
        self.assertTrue((self.root / "data").is_dir())
        # a running run is left alone
        (renamed / results.RUNNING).write_text(str(os.getpid()))
        self.assertEqual(self.post("/api/run-delete", {"ref": "A/backtests/" + renamed.name})[0], 400)
        row = [r for r in json.loads(self.get("/api/project?name=A")[1])["runs"] if r["name"] == renamed.name][0]
        self.assertTrue(row["running"])
        (renamed / results.RUNNING).write_text("999999999")          # a dead process: not running
        self.assertEqual(self.post("/api/run-delete", {"ref": "A/backtests/" + renamed.name})[0], 200)
        self.assertFalse(renamed.exists())

    def test_optimize_request_is_validated(self):
        status, body = self.post("/api/optimize", {"project": "A", "parameters": []})
        self.assertEqual(status, 400)
        self.assertIn("at least one", body["error"])
        status, body = self.post("/api/optimize", {"project": "A", "parameters": [
            {"name": "x", "min": "1", "max": "100000", "step": "1"}]})
        self.assertEqual(status, 400)
        self.assertIn("limit", body["error"])
        self.assertEqual(self.post("/api/optimize", {"project": "../outside", "parameters": []})[0], 400)

    def test_report_page(self):
        run = self.root / "A" / "backtests" / "2026-10-28_11-00-00"
        ref = urllib.request.quote("A/backtests/2026-10-28_11-00-00")
        self.assertEqual(self.get("/report?ref=" + ref)[0], 400)            # not made yet
        (run / "report.html").write_text("<html>report</html>")
        status, body = self.get("/report?ref=" + ref)
        self.assertEqual((status, body), (200, b"<html>report</html>"))
        self.assertTrue(json.loads(self.get("/api/run?ref=" + ref)[1])["report"])

    def test_downsample(self):
        pts = [[i, i] for i in range(10000)]
        out = gui.downsample(pts, 100)
        self.assertEqual(len(out), 100)
        self.assertEqual(out[0], [0, 0])
        self.assertEqual(out[-1], [9999, 9999])


if __name__ == "__main__":
    unittest.main()
