"""Live paper trading on daily KRX data (`klean live`, the GUI's Live dashboard).

A *deployment* freezes a project's code and gives it a paper account. Every day, after the
new KRX data is installed (`klean update data`), `run` processes each new trading day: one LEAN
process in live mode per day, with klean's plugin (klean/plugin: QuantConnect.Krx.dll):

- KrxDailyDataQueue delivers that day's bars;
- KrxPaperBrokerage keeps the account in ``ledger.json``: orders placed on one day are filled
  at the next trading day's open (KRX commission, sell tax, slippage in ticks), before the
  strategy runs, so it sees its fills; the run stops itself when the day is done.

The strategy is unchanged: LEAN ignores its start and end dates in live mode, as `lean live`
does. Its clock is the time of the run, not the day of the data (KRX publishes a day's prices
the next day): code that acts in on_data is unaffected; scheduled events fire on run time.

Folder: ``<project>/live/<id>/`` with ``deployment.json`` (settings, state), ``code/`` (the
frozen project), ``ledger.json`` (the account), ``runs/<day>/`` (each day's LEAN output).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

from klean import projects, results
from klean.workspace import KleanError, Workspace, dotnet
from klean.workspace import run as run_command

PLUGIN_SRC = Path(__file__).with_name("plugin")
PLUGIN_DLL = "QuantConnect.Krx.dll"
RECORD = "deployment.json"
LEDGER = "ledger.json"
LIVE_CONFIG = {
    "environment": "live-paper",
    "live-mode": True,
    "live-mode-brokerage": "KrxPaperBrokerage",
    "data-queue-handler": ["QuantConnect.Krx.KrxDailyDataQueue"],
    "setup-handler": "QuantConnect.Lean.Engine.Setup.BrokerageSetupHandler",
    "result-handler": "QuantConnect.Lean.Engine.Results.LiveTradingResultHandler",
    "data-feed-handler": "QuantConnect.Lean.Engine.DataFeeds.LiveTradingDataFeed",
    "real-time-handler": "QuantConnect.Lean.Engine.RealTime.LiveTradingRealTimeHandler",
    "transaction-handler": "QuantConnect.Lean.Engine.TransactionHandlers.BrokerageTransactionHandler",
}


# ---------------------------------------------------------------- the plugin

def plugin_path(ws: Workspace) -> Path:
    return ws.launcher_dir / PLUGIN_DLL


def ensure_plugin(ws: Workspace, log=print) -> Path:
    """Build klean's LEAN plugin into the LEAN build if it's missing or older than its sources
    or than LEAN itself (rebuilt LEAN: rebuild the plugin against it)."""
    dll = plugin_path(ws)
    sources = [*PLUGIN_SRC.glob("*.cs"), *PLUGIN_SRC.glob("*.csproj"), projects.CS_MODELS]
    lean = ws.launcher_dir / "QuantConnect.Lean.Engine.dll"
    if dll.exists() and dll.stat().st_mtime >= max(p.stat().st_mtime for p in [*sources, lean]):
        return dll
    log(f"klean: building the KRX live plugin into {ws.launcher_dir}")
    out = Path(ws.root) / ".klean" / "plugin-build"
    run_command([dotnet(), "build", str(PLUGIN_SRC / "Krx.Lean.csproj"), "-c", "Release", "-nologo", "-v", "q",
         f"-p:LeanBin={ws.launcher_dir}", "-o", str(out)])
    shutil.copy2(out / PLUGIN_DLL, dll)
    return dll


# ---------------------------------------------------------------- trading days

def trading_days(ws: Workspace) -> list[str]:
    """KRX trading days in the data (YYYY-MM-DD), from the KOSPI index file."""
    path = ws.data / "index" / "krx" / "daily" / "kospi.zip"
    if not path.exists():
        raise KleanError(f"no {path}: the KRX index data is needed for the trading calendar")
    with zipfile.ZipFile(path) as z:
        lines = z.read(z.namelist()[0]).decode().splitlines()
    return [f"{x[:4]}-{x[4:6]}-{x[6:8]}" for x in (line[:8] for line in lines if len(line) >= 8)]


# ---------------------------------------------------------------- deployments

def live_dir(project: Path) -> Path:
    return project / "live"


def deployments(project: Path) -> list[Path]:
    d = live_dir(project)
    return sorted(t for t in d.iterdir() if (t / RECORD).exists()) if d.is_dir() else []


def load(dep: Path) -> dict:
    return json.loads((dep / RECORD).read_text(encoding="utf-8"))


def save(dep: Path, record: dict) -> None:
    tmp = dep / (RECORD + ".tmp")
    tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(dep / RECORD)


def ledger(dep: Path) -> dict:
    return json.loads((dep / LEDGER).read_text(encoding="utf-8"))


def find(project: Path, dep_id: str) -> Path:
    dep = live_dir(project) / dep_id
    if dep.parent != live_dir(project) or not (dep / RECORD).exists():
        raise KleanError(f"no live deployment {dep_id!r} in {project.name} (`klean live status {project.name}`)")
    return dep


def deploy(ws: Workspace, project: Path, name: str = "", parameters: dict[str, str] | None = None,
           cash: float = 100_000_000, commission_rate: float = 0.00015, start: str = "",
           source_run: str = "") -> Path:
    """Freeze the project's code and open a paper account. Trading starts on the first trading
    day after the latest data (``start``, YYYY-MM-DD, can set an earlier day: a *backdated*
    deployment, labeled so, for trying it on days the data already has)."""
    project = project.resolve()
    language = projects.language_of(project)
    days = trading_days(ws)
    last = days[-1]
    first = start or (dt.date.fromisoformat(last) + dt.timedelta(days=1)).isoformat()
    params = {str(k): str(v) for k, v in (parameters or {}).items()}
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    dep = live_dir(project) / (f"{stamp}_{safe}" if safe else stamp)
    if dep.exists():
        raise KleanError(f"{dep} already exists")
    dep.mkdir(parents=True)
    try:
        results.snapshot_code(project, dep / "code")
        # the session before the first one: the ledger's starting point
        before = [d for d in days if d < first]
        (dep / LEDGER).write_text(json.dumps({
            "currency": "KRW", "cash": cash, "commission_rate": commission_rate,
            "slippage_ticks": int(params.get("slippage_ticks", "0") or 0),
            "holdings": {}, "open_orders": [], "next_order_id": 1, "fills": [], "events": [],
            "equity": [], "last_session": before[-1] if before else "", "start_cash": cash,
        }, indent=2) + "\n", encoding="utf-8")
        save(dep, {"id": dep.name, "name": name or dep.name, "project": project.name, "language": language,
                   "parameters": params, "source_run": source_run, "cash": cash, "commission_rate": commission_rate,
                   "first_session": first, "backdated": first <= last, "data_last_date_at_start": last,
                   "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "synthetic_demo_data": results.is_demo_data(ws), "broker": "paper",
                   "status": "running", "runs": []})
    except BaseException:
        shutil.rmtree(dep, ignore_errors=True)
        raise
    return dep


def pending_sessions(ws: Workspace, dep: Path) -> list[str]:
    """Trading days in the data the deployment hasn't processed yet, in order."""
    record, book = load(dep), ledger(dep)
    done = book.get("last_session") or ""
    return [d for d in trading_days(ws) if d >= record["first_session"] and d > done]


def run_session(ws: Workspace, dep: Path, session: str, timeout: float = 900, log=print) -> dict:
    """One trading day: LEAN in live mode with klean's plugin. Returns the run's entry."""
    from klean.backtest import launcher_args, prepare, write_run_config
    record = load(dep)
    code = dep / "code"
    language = projects.language_of(code)
    location, cls, env = prepare(ws, code, language)
    out = dep / "runs" / session
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    config = write_run_config(ws, out, {
        **ws.lean_config, **LIVE_CONFIG,
        "krx-ledger": str(dep / LEDGER), "krx-session-date": session,
        "live-cash-balance": "", "live-holdings": "[]",
        "algorithm-id": f"klean-{record['project']}-{dep.name}",
    })
    cfg = json.loads(config.read_text(encoding="utf-8"))
    cfg["environments"] = {k: v for k, v in cfg.get("environments", {}).items() if k == "backtesting"}
    config.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    args = launcher_args(ws, language, location, cls, out, record["parameters"], config, f"live {record['name']}")
    log(f"klean: live {record['project']}/{dep.name}: trading day {session}")
    started = time.monotonic()
    with open(out / "console.txt", "w", encoding="utf-8") as console:
        proc = subprocess.Popen(args, cwd=ws.launcher_dir, env={**os.environ, **env}, stdout=console,
                                stderr=subprocess.STDOUT)
        try:
            code_ = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            code_ = -9
    book = ledger(dep)
    ok = book.get("last_session") == session
    text = (out / "console.txt").read_text(encoding="utf-8", errors="replace")
    error = ""
    if not ok:
        match = re.findall(r"(?:ERROR::|Runtime Error:|Exception:)\s*(.+)", text)
        error = (match[-1] if match else f"LEAN exited ({code_}) before the day was processed").strip()[:400]
    equity = next((e["equity"] for e in reversed(book.get("equity", [])) if e["session"] == session), None)
    entry = {"session": session, "ok": ok, "seconds": round(time.monotonic() - started, 1), "exit_code": code_,
             "equity": equity, "orders": sum(1 for o in book.get("open_orders", []) if o.get("placed_session") == session),
             "fills": sum(1 for f in book.get("fills", []) if f.get("session") == session),
             **({"error": error} if error else {})}
    record = load(dep)
    record["runs"] = [r for r in record["runs"] if r["session"] != session] + [entry]
    save(dep, record)
    return entry


def run(ws: Workspace, dep: Path, log=print, max_sessions: int = 0) -> list[dict]:
    """Process every trading day the deployment hasn't seen yet, oldest first; stops at the
    first failure (the next run retries it)."""
    if load(dep)["status"] != "running":
        return []
    ensure_plugin(ws, log)
    done = []
    for session in pending_sessions(ws, dep)[: max_sessions or None]:
        entry = run_session(ws, dep, session, log=log)
        done.append(entry)
        if not entry["ok"]:
            log(f"klean: live {dep.name}: {session} FAILED: {entry.get('error')}")
            break
    return done


def run_all(ws: Workspace, log=print) -> list[tuple[str, list[dict]]]:
    """Every running deployment in the workspace (after a data update)."""
    out = []
    for project in projects.list_projects(ws):
        for dep in deployments(project):
            if load(dep)["status"] == "running":
                out.append((f"{project.name}/{dep.name}", run(ws, dep, log)))
    return out


def stop(dep: Path) -> dict:
    record = load(dep)
    if record["status"] != "stopped":
        record.update(status="stopped", stopped_utc=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        save(dep, record)
    return record


def summary(ws: Workspace, dep: Path) -> dict:
    record, book = load(dep), ledger(dep)
    equity = book.get("equity", [])
    last_run = record["runs"][-1] if record["runs"] else None
    if record["status"] == "stopped":
        state = "stopped"
    elif last_run and not last_run["ok"]:
        state = "failed"
    elif not equity:
        state = "waiting for data"
    else:
        state = "running"
    start_cash = book.get("start_cash") or record["cash"]
    end = equity[-1]["equity"] if equity else start_cash
    return {**{k: v for k, v in record.items() if k != "runs"}, "state": state, "days": len(equity),
            "last_session": book.get("last_session", ""), "last_run": last_run,
            "equity": end, "net_profit": (end / start_cash - 1) * 100 if start_cash else 0.0,
            "cash": book.get("cash"), "holdings": len(book.get("holdings", {})),
            "open_orders": len(book.get("open_orders", []))}
