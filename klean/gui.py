"""`klean gui`: a local web page for the workspace: projects, runs, results charts, comparisons,
optimizations, LEAN reports, and starting backtests. Standard library only; the page draws its charts itself (no CDN).

Safety: listens on 127.0.0.1 only, every request needs the random token in the URL printed at
start-up (so other web pages in the browser can't call it), and every project or run it touches
must be inside the workspace.
"""

from __future__ import annotations

import json
import platform
import re
import secrets
import shutil
import signal
import socketserver
import subprocess
import threading
import time
import traceback
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import urllib.request
from urllib.parse import parse_qs, urlparse

from klean import __version__, projects, results
from klean.backtest import backtest, results_folder
from klean.report import report
from klean.workspace import KleanError, Workspace, check

STATIC = Path(__file__).with_name("static")
# The page's own files: scripts and styles from klean/static only (no CDN), inline style
# attributes for layout, no inline scripts.
PAGE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-src 'self' http://127.0.0.1:*; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
STATIC_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


def static_file(path: str) -> Path | None:
    """A file under klean/static for a /static/... URL, or None (also for anything outside it)."""
    target = (STATIC / path.removeprefix("/static/")).resolve()
    if STATIC.resolve() in target.parents and target.suffix in STATIC_TYPES and target.is_file():
        return target
    return None
# LEAN's report: inline styles and data: images, plus its stylesheets, fonts and logo from CDNs; no scripts.
REPORT_CSP = ("default-src 'none'; img-src data: https://cdn.quantconnect.com; style-src 'unsafe-inline' "
              "https://fonts.googleapis.com https://cdnjs.cloudflare.com; font-src https://fonts.gstatic.com "
              "https://cdnjs.cloudflare.com")
MAX_POINTS = 1500
ORDER_TYPES = {0: "Market", 1: "Limit", 2: "StopMarket", 3: "StopLimit", 4: "MarketOnOpen", 5: "MarketOnClose",
               6: "OptionExercise", 7: "LimitIfTouched", 8: "ComboMarket", 9: "ComboLimit", 10: "ComboLegLimit",
               11: "TrailingStop"}
ORDER_STATUS = {0: "New", 1: "Submitted", 2: "PartiallyFilled", 3: "Filled", 5: "Canceled", 6: "None",
                7: "Invalid", 8: "CancelPending", 9: "UpdateSubmitted"}


# ---------------------------------------------------------------- helpers

def inside(ws: Workspace, path: Path) -> Path:
    path = path.resolve()
    if path != ws.root and ws.root not in path.parents:
        raise KleanError(f"{path} is outside the workspace")
    return path


def run_ref(ws: Workspace, ref: str) -> Path:
    return inside(ws, results.resolve_run(ws, ref))


def downsample(points: list, n: int = MAX_POINTS) -> list:
    if len(points) <= n:
        return points
    step = len(points) / n
    out = [points[int(i * step)] for i in range(n)]
    out[-1] = points[-1]
    return out


def series(chart: dict, name: str, close: bool = False) -> list[list[float]]:
    values = chart.get("series", {}).get(name, {}).get("values", [])
    return [[int(v[0]), float(v[4] if close and len(v) > 4 else v[1])] for v in values if v[1] is not None]


def full_result(run: Path) -> dict:
    summary = results.summary_file(run)
    path = run / summary.name.replace("-summary.json", ".json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def manifest(run: Path) -> dict:
    p = run / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def code_dir(run: Path) -> Path:
    """The run's code snapshot: <run>/code, or the optimization's shared one (../code)."""
    return (run / manifest(run).get("code", "code/")).resolve()


def project_list(ws: Workspace) -> list[Path]:
    out = projects.list_projects(ws)
    return out


def run_row(run: Path) -> dict:
    try:
        stats = results.statistics(run)
    except KleanError:
        stats = {}
    m = manifest(run)
    error = results.run_error(run)
    running = results.is_running(run)
    if running:
        error = ""
    return {"ref": f"{run.parent.parent.name}/{run.name}", "name": run.name, "running": running,
            "ok": running or (bool(stats) and not error),
            "error": error.splitlines()[0] if error else "", "demo": bool(m.get("synthetic_demo_data")),
            "stats": {k: stats.get(k, "") for k in ("Compounding Annual Return", "Drawdown", "Sharpe Ratio",
                                                     "Total Orders", "End Equity")},
            "parameters": m.get("parameters", {}), "seconds": m.get("seconds")}


# ---------------------------------------------------------------- API

def api_workspace(ws: Workspace, _q: dict) -> dict:
    rows = []
    for p in project_list(ws):
        runs = results.runs(p)
        rows.append({"name": p.name, "language": projects.language_of(p), "runs": len(runs),
                     "last": run_row(runs[-1]) if runs else None})
    try:
        data = results.data_status(ws)
    except Exception as e:  # noqa: BLE001
        data = {"error": str(e)}
    return {"root": str(ws.root), "version": __version__, "lean_root": ws.lean_root,
            "python_venv": ws.python_venv, "lean_config": ws.lean_config, "projects": rows, "data": data,
            "doctor": [{"item": i, "ok": ok, "detail": d} for i, ok, d in [*check(ws), projects.models_row(ws)]],
            "templates": list(projects.TEMPLATES)}


def api_project(ws: Workspace, q: dict) -> dict:
    p = inside(ws, ws.root / q["name"][0])
    lang = projects.language_of(p)
    files = sorted(f.relative_to(p).as_posix() for f in p.rglob("*") if f.is_file()
                   and f.relative_to(p).parts[0] not in results.OUTPUT_DIRS)
    return {"name": p.name, "language": lang, "files": files,
            "runs": [run_row(r) for r in reversed(results.runs(p))],
            "optimizations": [opt_row(o) for o in reversed(optimizations(p))]}


def optimizations(project: Path) -> list[Path]:
    d = project / "optimizations"
    return sorted(o for o in d.iterdir() if (o / "optimization.json").exists()) if d.is_dir() else []


def opt_row(opt: Path) -> dict:
    o = json.loads((opt / "optimization.json").read_text(encoding="utf-8"))
    best = next((r for r in o["runs"] if r["folder"] == o.get("best")), None)
    return {"name": opt.name, "target": o["target"], "direction": o["direction"], "runs": len(o["runs"]),
            "parameters": [p["name"] for p in o["parameters"]], "seconds": o.get("seconds"),
            "best": {"parameters": best["parameters"], "target": best["stats"].get(o["target"]) or best["target_value"]}
            if best else None}


def api_optimization(ws: Workspace, q: dict) -> dict:
    from klean.optimize import ranked, ranking
    project = inside(ws, ws.root / q["project"][0])
    name = q["name"][0]
    opt = inside(ws, project / "optimizations" / name)
    if "/" in name or name.startswith(".") or not (opt / "optimization.json").exists():
        raise KleanError(f"no optimization {name!r} in {project.name}")
    o = json.loads((opt / "optimization.json").read_text(encoding="utf-8"))
    header, rows = ranking(o)
    by_index = sorted(o["runs"], key=lambda r: r["index"])
    refs = {r["folder"]: f"{project.name}/optimizations/{opt.name}/{r['folder']}" for r in o["runs"]}
    order = [r["folder"] for r in ranked(o)]   # table rows are in ranking order
    return {**o, "name": opt.name, "header": header, "rows": rows, "row_refs": [refs[f] for f in order],
            "refs": refs, "points": [[r["parameters"], r["target_value"], r["ok"] and r["passes"]] for r in by_index]}


def api_run(ws: Workspace, q: dict) -> dict:
    run = run_ref(ws, q["ref"][0])
    full = full_result(run)
    charts = full.get("charts", {})
    equity = series(charts.get("Strategy Equity", {}), "Equity", close=True)
    bench = series(charts.get("Benchmark", {}), "Benchmark")
    if equity and bench:                  # benchmark rescaled to the starting equity
        b0 = next((v for _, v in bench if v), 0)
        bench = [[t, v / b0 * equity[0][1]] for t, v in bench] if b0 else []
    drawdown = series(charts.get("Drawdown", {}), "Equity Drawdown")
    orders = []
    for o in sorted(full.get("orders", {}).values(), key=lambda o: o.get("id", 0)):
        orders.append({"id": o.get("id"), "time": o.get("time"), "symbol": o.get("symbol", {}).get("value"),
                       "type": ORDER_TYPES.get(o.get("type"), o.get("type")),
                       "status": ORDER_STATUS.get(o.get("status"), o.get("status")),
                       "quantity": o.get("quantity"), "price": o.get("price"), "value": o.get("value"),
                       "tag": o.get("tag", "")})
    try:
        log = results.log_text(run).splitlines()[-200:]
    except KleanError:
        log = []
    return {"ref": run.relative_to(ws.root).as_posix(), "folder": str(run),
            "statistics": results.statistics(run), "runtime": full.get("runtimeStatistics", {}),
            "equity": downsample(equity), "benchmark": downsample(bench), "drawdown": downsample(drawdown),
            "orders": orders, "manifest": manifest(run), "log": log, "report": (run / "report.html").exists(),
            "error": "" if results.is_running(run) else results.run_error(run),
            "running": results.is_running(run), "demo": results.run_is_demo(run),
            "code": [p.relative_to(code_dir(run)).as_posix() for p in sorted(code_dir(run).rglob("*")) if p.is_file()]
            if code_dir(run).is_dir() else []}


def api_code_file(ws: Workspace, q: dict) -> dict:
    root = code_dir(run_ref(ws, q["ref"][0]))
    path = inside(ws, root / q["path"][0])
    if root not in path.parents or not path.is_file():
        raise KleanError("no such file in the code snapshot")
    data = path.read_bytes()
    if len(data) > 2_000_000 or b"\0" in data[:8000]:
        return {"path": q["path"][0], "text": None, "bytes": len(data)}
    return {"path": q["path"][0], "text": data.decode("utf-8", errors="replace"), "bytes": len(data)}


def api_compare(ws: Workspace, q: dict) -> dict:
    refs = q.get("ref", [])
    if len(refs) < 2:
        raise KleanError("choose at least two runs")
    runs = [run_ref(ws, r) for r in refs]
    header, rows, verdict = results.compare(runs, all_keys="all" in q)
    curves = [{"label": results.label(r), "points": downsample([list(p) for p in results.equity_curve(r)])}
              for r in runs]
    return {"header": header, "rows": rows, "verdict": verdict, "curves": curves,
            "refs": [r.relative_to(ws.root).as_posix() for r in runs]}


def api_log(ws: Workspace, q: dict) -> dict:
    run = run_ref(ws, q["ref"][0])
    return {"lines": results.log_text(run, console="console" in q).splitlines()[-int(q.get("tail", ["500"])[0]):]}


def stored_run(ws: Workspace, ref: str) -> Path:
    """A run folder that may be renamed or deleted: directly under a project's backtests/."""
    run = inside(ws, ws.root / ref)
    if not run.is_dir() or run.parent.name != "backtests" or run.parent.parent.parent != ws.root:
        raise KleanError("only runs in a project's backtests/ folder can be renamed or deleted")
    if results.is_running(run):
        raise KleanError("this run is still running")
    return run


def api_run_delete(ws: Workspace, body: dict) -> dict:
    run = stored_run(ws, str(body.get("ref", "")))
    shutil.rmtree(run)
    return {"deleted": run.name}


def api_run_rename(ws: Workspace, body: dict) -> dict:
    """Change the name part of a run folder (``<timestamp>[_<name>]``); the timestamp stays."""
    run = stored_run(ws, str(body.get("ref", "")))
    stamp = re.match(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", run.name)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", str(body.get("name", ""))).strip("-")
    if not stamp:
        raise KleanError("this run's folder doesn't start with a timestamp; rename it by hand")
    target = run.with_name(f"{stamp.group(0)}_{safe}" if safe else stamp.group(0))
    if target == run:
        return {"ref": run.relative_to(ws.root).as_posix()}
    if target.exists():
        raise KleanError(f"{target.name} already exists")
    run.rename(target)
    return {"ref": target.relative_to(ws.root).as_posix()}


class Jobs:
    """Backtests and reports started from the page, each in a thread (LEAN runs as a separate process)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}
        self.notebook: dict = {}            # the workspace's JupyterLab (Research tab)

    def start(self, ws: Workspace, body: dict) -> dict:
        project = inside(ws, ws.root / str(body.get("project", "")))
        projects.language_of(project)
        params = {str(k): str(v) for k, v in (body.get("parameters") or {}).items() if str(k)}
        extra = {str(k): str(v) for k, v in (body.get("extraConfig") or {}).items() if str(k)}
        name = str(body.get("backtestName") or "")
        out = results_folder(project, None, name)
        job = {"id": secrets.token_hex(4), "project": project.name, "folder": str(out),
               "ref": f"{project.name}/{out.name}", "status": "building", "error": "", "started": time.time()}
        with self.lock:
            self.jobs[job["id"]] = job

        def work():
            try:
                job["status"] = "running"
                backtest(ws, project, params, extra_config=extra, output=out, backtest_name=name)
                job["status"] = "done"
            except Exception as e:  # noqa: BLE001 - reported to the page
                job["status"], job["error"] = "failed", str(e)
                if out.is_dir() and not any(out.iterdir()):     # e.g. the build failed: no run to keep
                    out.rmdir()
            job["finished"] = time.time()
        threading.Thread(target=work, daemon=True).start()
        return job

    def start_report(self, ws: Workspace, body: dict) -> dict:
        run = run_ref(ws, str(body.get("ref", "")))
        results.summary_file(run)
        job = {"id": secrets.token_hex(4), "kind": "report", "ref": run.relative_to(ws.root).as_posix(),
               "folder": str(run), "console_file": "report-console.txt", "status": "running", "error": "",
               "started": time.time()}
        with self.lock:
            if any(j.get("kind") == "report" and j["ref"] == job["ref"] and j["status"] == "running"
                   for j in self.jobs.values()):
                raise KleanError("a report for this run is already being made")
            self.jobs[job["id"]] = job

        def work():
            try:
                report(ws, run, overwrite=True, log=lambda *a: None)
                job["status"] = "done"
            except Exception as e:  # noqa: BLE001 - reported to the page
                job["status"], job["error"] = "failed", str(e)
            job["finished"] = time.time()
        threading.Thread(target=work, daemon=True).start()
        return job

    def start_optimize(self, ws: Workspace, body: dict) -> dict:
        from klean import optimize
        project = inside(ws, ws.root / str(body.get("project", "")))
        projects.language_of(project)
        specs = [(str(p.get("name", "")).strip(), str(p.get("min", "")), str(p.get("max", "")), str(p.get("step", "")))
                 for p in (body.get("parameters") or []) if str(p.get("name", "")).strip()]
        constraints = [str(c) for c in (body.get("constraints") or []) if str(c).strip()]
        options = dict(target=str(body.get("target") or "Sharpe Ratio"), direction=str(body.get("direction") or "max"),
                       constraints=constraints, max_concurrent=int(body.get("maxConcurrent") or 0),
                       name=str(body.get("name") or ""))
        estimate = optimize.optimize(ws, project, specs, estimate=True, **options)     # validates the input
        if estimate["backtests"] > optimize.MAX_BACKTESTS:
            raise KleanError(f"{estimate['backtests']} combinations; the limit is {optimize.MAX_BACKTESTS}")
        lines: list[str] = []
        job = {"id": secrets.token_hex(4), "kind": "optimize", "project": project.name, "folder": "", "ref": "",
               "status": "running", "error": "", "started": time.time(), "lines": lines,
               "backtests": estimate["backtests"]}
        with self.lock:
            self.jobs[job["id"]] = job

        def work():
            try:
                s = optimize.optimize(ws, project, specs, log=lambda *a: lines.append(" ".join(map(str, a))), **options)
                job["folder"], job["ref"] = s["folder"], Path(s["folder"]).name
                job["status"] = "done"
            except Exception as e:  # noqa: BLE001 - reported to the page
                job["status"], job["error"] = "failed", str(e)
            job["finished"] = time.time()
        threading.Thread(target=work, daemon=True).start()
        return {k: v for k, v in job.items() if k != "lines"}

    def research(self, ws: Workspace, body: dict | None, gui_port: int) -> dict:
        """The workspace's JupyterLab, shown in the page's Research tab: started on the first POST
        (installing JupyterLab into the Python env the first time), stopped with the GUI. GET
        (body None) only reports its state. With a project, also its notebook's address."""
        from klean import research
        project = None
        if body and body.get("project"):
            project = inside(ws, ws.root / str(body["project"]))
            projects.language_of(project)
        with self.lock:
            nb = self.notebook
            alive = nb.get("proc") is not None and nb["proc"].poll() is None
            if nb.get("status") == "ready" and not alive:          # JupyterLab exited
                nb.clear()
                nb.update(status="stopped", error="JupyterLab stopped (see .klean/research/jupyter.log)")
            if body is not None and nb.get("status") not in ("installing", "starting", "ready"):
                nb.clear()
                nb.update(status="starting", error="", started=time.time())
                threading.Thread(target=self._start_notebook, args=(ws, gui_port), daemon=True).start()
            state = {k: v for k, v in nb.items() if k in ("status", "error", "started")}
        if not state:
            state = {"status": "off"}
        if state["status"] == "ready":
            base = f"http://127.0.0.1:{nb['port']}"
            state["url"] = f"{base}/lab?token={nb['token']}"
            if project is not None:
                notebook = research.ensure_notebook(ws, project)
                state["url"] = f"{base}/lab/tree/{project.name}/{notebook.name}?token={nb['token']}"
        return state

    def _start_notebook(self, ws: Workspace, gui_port: int) -> None:
        from klean import research
        nb = self.notebook
        try:
            if not research.packages_installed(ws):
                nb["status"] = "installing"
                research.ensure_packages(ws, log=lambda *a: None)
            nb["status"] = "starting"
            folder = research.research_dir(ws)
            folder.mkdir(parents=True, exist_ok=True)
            log = open(folder / "jupyter.log", "w")
            origins = f"http://127.0.0.1:{gui_port} http://localhost:{gui_port}"
            proc, port, token = research.start_workspace_server(ws, origins, output=log)
            nb.update(proc=proc, port=port, token=token)
            deadline = time.time() + 120
            while time.time() < deadline:
                if proc.poll() is not None:
                    raise KleanError(f"JupyterLab exited ({proc.returncode}); see {folder / 'jupyter.log'}")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status?token={token}", timeout=2):
                        nb["status"] = "ready"
                        return
                except OSError:
                    time.sleep(0.5)
            raise KleanError(f"JupyterLab didn't answer in 2 minutes; see {folder / 'jupyter.log'}")
        except Exception as e:  # noqa: BLE001 - shown on the page
            nb.update(status="failed", error=str(e))

    def stop_all(self) -> None:
        proc = self.notebook.get("proc")
        if proc is not None and proc.poll() is None:
            proc.terminate()                  # JupyterLab shuts its kernels down first
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    def status(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if job is None:
            raise KleanError("unknown job")
        if job.get("kind") == "optimize":
            return {**{k: v for k, v in job.items() if k != "lines"}, "console": job["lines"][-40:]}
        console = Path(job["folder"]) / job.get("console_file", "console.txt")
        tail = console.read_text(encoding="utf-8", errors="replace").splitlines()[-40:] if console.exists() else []
        return {**job, "console": tail}

    def all(self) -> list[dict]:
        return sorted(({k: v for k, v in j.items() if k != "lines"} for j in self.jobs.values()),
                      key=lambda j: -j["started"])


# ---------------------------------------------------------------- server

def make_handler(ws: Workspace, token: str, jobs: Jobs):
    gets = {"/api/workspace": api_workspace, "/api/project": api_project, "/api/run": api_run,
            "/api/compare": api_compare, "/api/log": api_log, "/api/optimization": api_optimization,
            "/api/code-file": api_code_file}

    class Handler(BaseHTTPRequestHandler):
        server_version = f"klean-gui/{__version__}"

        def log_message(self, fmt, *args):   # quiet; errors are returned to the page
            pass

        def _authorized(self, q: dict) -> bool:
            given = self.headers.get("X-Klean-Token") or (q.get("token") or [""])[0]
            return secrets.compare_digest(given, token)

        def _send(self, status: int, body: bytes, ctype: str, headers: dict | None = None) -> None:
            self.send_response(status)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status: int = 200) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            q = parse_qs(url.query)
            if url.path.startswith("/static/"):     # code and styles, no data: served without the token
                f = static_file(url.path)
                if f is None:
                    self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
                else:
                    self._send(200, f.read_bytes(), STATIC_TYPES[f.suffix])
                return
            if not self._authorized(q):
                self._send(HTTPStatus.FORBIDDEN, b"Open the URL printed by `klean gui` (it includes the access token).",
                           "text/plain; charset=utf-8")
                return
            if url.path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8",
                           {"Content-Security-Policy": PAGE_CSP})
                return
            try:
                if url.path in gets:
                    self._json(gets[url.path](Workspace.load(ws.root), q))
                elif url.path == "/report":
                    page = run_ref(ws, q["ref"][0]) / "report.html"
                    if not page.exists():
                        raise KleanError("no report for this run yet")
                    self._send(200, page.read_bytes(), "text/html; charset=utf-8", {"Content-Security-Policy": REPORT_CSP})
                elif url.path == "/api/research":
                    self._json(jobs.research(Workspace.load(ws.root), None, self.server.server_address[1]))
                elif url.path == "/api/jobs":
                    self._json(jobs.all())
                elif url.path == "/api/job":
                    self._json(jobs.status(q["id"][0]))
                else:
                    self._json({"error": "not found"}, 404)
            except (KleanError, KeyError, ValueError) as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                self._json({"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}, 500)

        def do_POST(self):  # noqa: N802
            url = urlparse(self.path)
            if not self._authorized(parse_qs(url.query)) or self.headers.get("X-Klean-Token") is None:
                self._send(HTTPStatus.FORBIDDEN, b"forbidden", "text/plain")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                if url.path == "/api/backtest":
                    self._json(jobs.start(Workspace.load(ws.root), body))
                elif url.path == "/api/report":
                    self._json(jobs.start_report(Workspace.load(ws.root), body))
                elif url.path == "/api/optimize":
                    self._json(jobs.start_optimize(Workspace.load(ws.root), body))
                elif url.path == "/api/research":
                    self._json(jobs.research(Workspace.load(ws.root), body, self.server.server_address[1]))
                elif url.path == "/api/run-delete":
                    self._json(api_run_delete(Workspace.load(ws.root), body))
                elif url.path == "/api/run-rename":
                    self._json(api_run_rename(Workspace.load(ws.root), body))
                else:
                    self._json({"error": "not found"}, 404)
            except (KleanError, ValueError) as e:
                self._json({"error": str(e)}, 400)

    return Handler


class LocalServer(ThreadingHTTPServer):
    """ThreadingHTTPServer without the reverse DNS lookup of its address (`socket.getfqdn` in
    HTTPServer.server_bind), which can hang for a long time on some systems (seen on macOS)."""

    daemon_threads = True

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def open_page(url: str) -> None:
    """The default browser; under WSL the Windows one (wslview, from wslu) if it's installed."""
    if "microsoft" in platform.release().lower() and shutil.which("wslview"):
        subprocess.Popen(["wslview", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(url)


def serve(ws: Workspace, port: int = 0, open_browser: bool = True, token: str | None = None) -> None:
    token = token or secrets.token_urlsafe(24)
    jobs = Jobs()
    server = LocalServer(("127.0.0.1", port), make_handler(ws, token, jobs))
    url = f"http://127.0.0.1:{server.server_address[1]}/?token={token}"
    print(f"klean gui for {ws.root}\n  {url}\n(Ctrl+C to stop)", flush=True)
    if open_browser:
        threading.Timer(0.5, lambda: open_page(url)).start()
    def stop(*_):                 # `kill` should clean up like Ctrl+C does
        raise KeyboardInterrupt
    try:
        signal.signal(signal.SIGTERM, stop)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, stop)     # the terminal was closed
    except ValueError:            # not the main thread (tests)
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        jobs.stop_all()          # notebooks started from the page
        server.server_close()
