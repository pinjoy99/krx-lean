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


def krx_holidays(ws: Workspace) -> set[str]:
    """KRX holidays (YYYY-MM-DD) from LEAN's market-hours database in the workspace."""
    path = ws.data / "market-hours" / "market-hours-database.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
    except (OSError, ValueError, KeyError):
        return set()
    entry = next((v for k, v in entries.items() if k.lower().startswith("equity-krx")), {})
    out = set()
    for h in entry.get("holidays", []):
        try:
            out.add(dt.datetime.strptime(h, "%m/%d/%Y").date().isoformat())
        except ValueError:
            pass
    return out


def is_trading_day(ws: Workspace, day: dt.date, holidays: set[str] | None = None) -> bool:
    holidays = krx_holidays(ws) if holidays is None else holidays
    return day.weekday() < 5 and day.isoformat() not in holidays


def previous_trading_day(ws: Workspace, day: dt.date) -> str:
    holidays = krx_holidays(ws)
    d = day - dt.timedelta(days=1)
    while not is_trading_day(ws, d, holidays):
        d -= dt.timedelta(days=1)
    return d.isoformat()


# ---------------------------------------------------------------- deployments

def live_dir(project: Path) -> Path:
    return project / "live"


BROKERS = ("paper", "kis-paper")


def is_kis(record: dict) -> bool:
    """A KIS-PAPER deployment (named "kis" in 0.0.20)."""
    return record.get("broker") in ("kis-paper", "kis")


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
           source_run: str = "", models_as_is: bool = False, broker: str = "paper") -> Path:
    """Freeze the project's code and open a paper account. Trading starts on the first trading
    day after the latest data (``start``, YYYY-MM-DD, can set an earlier day: a *backdated*
    deployment, labeled so, for trying it on days the data already has)."""
    project = project.resolve()
    language = projects.language_of(project)
    state = projects.models_state(project)
    if state != "current" and not models_as_is:
        what = "missing" if state == "missing" else "not krx-lean's current one (older, or edited)"
        raise KleanError(
            f"{project.name}'s copy of the KRX models is {what}; live runs need the current one (it reads the "
            f"KRX universe in live mode). Run `klean update models {project.name}` (your copy is kept as .bak), "
            "or deploy with --models-as-is if you edited it on purpose")
    days = trading_days(ws)
    last = days[-1]
    first = start or (dt.date.fromisoformat(last) + dt.timedelta(days=1)).isoformat()
    account_id = ""
    if broker == "kis-paper":
        from klean import kis
        if start:
            raise KleanError("a KIS-PAPER deployment can't be backdated: it trades from the next pre-open auction")
        client = kis.Kis()
        account_id = client.account_id()
        for other_project in projects.list_projects(ws):
            for other in deployments(other_project):
                o = load(other)
                if is_kis(o) and o["status"] == "running" and o.get("kis_account") == account_id:
                    raise KleanError(
                        f"{other_project.name}/{other.name} already trades this KIS account: a strategy sees the whole "
                        "account (cash and every holding) as its own, so two can't share one. Stop it first, or use "
                        "another account")
        account = client.balance()               # also checks the credentials
        cash = account["total"] or account["cash"]
        first = previous_trading_day(ws, kis.now_kst().date() + dt.timedelta(days=1))
    elif broker != "paper":
        raise KleanError(f"unknown broker {broker!r} (paper, kis-paper)")
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
            "broker": broker,
        }, indent=2) + "\n", encoding="utf-8")
        save(dep, {"id": dep.name, "name": name or dep.name, "project": project.name, "language": language,
                   "parameters": params, "source_run": source_run, "cash": cash, "commission_rate": commission_rate,
                   "first_session": first, "backdated": first <= last, "data_last_date_at_start": last,
                   "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "synthetic_demo_data": results.is_demo_data(ws), "broker": broker,
                   **({"kis_account": account_id} if broker == "kis-paper" else {}),
                   "status": "running", "runs": []})
    except BaseException:
        shutil.rmtree(dep, ignore_errors=True)
        raise
    return dep


def pending_sessions(ws: Workspace, dep: Path) -> list[str]:
    """Trading days the deployment hasn't processed yet, in order. Paper: every day in the data.
    KIS-PAPER: the previous trading day (prices from KIS), once; a broker can't trade past days."""
    record, book = load(dep), ledger(dep)
    done = book.get("last_session") or ""
    if is_kis(record):
        from klean import kis
        day = previous_trading_day(ws, kis.now_kst().date())
        return [day] if day > done and day >= record["first_session"] else []
    return [d for d in trading_days(ws) if d >= record["first_session"] and d > done]


def run_session(ws: Workspace, dep: Path, session: str, timeout: float = 900, log=print, now: bool = False) -> dict:
    """One trading day: LEAN in live mode with klean's plugin. Returns the run's entry."""
    from klean.backtest import launcher_args, prepare, write_run_config
    record = load(dep)
    code = dep / "code"
    language = projects.language_of(code)
    location, cls, env = prepare(ws, code, language)
    out = dep / "runs" / session
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    backup = dep / (LEDGER + ".before")          # the account as it was, restored if the day fails
    shutil.copy2(dep / LEDGER, backup)
    config = write_run_config(ws, out, {
        **ws.lean_config, **LIVE_CONFIG,
        **({"live-mode-brokerage": "KisPaperBrokerage", "krx-kis-prices": True, "krx-kis-any-time": now}
           if is_kis(record) else {}),
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
        proc = subprocess.Popen(args, cwd=ws.launcher_dir, env={**os.environ, **env, "KRX_SESSION_DATE": session},
                                stdout=console,
                                stderr=subprocess.STDOUT)
        try:
            code_ = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            code_ = -9
    text = (out / "console.txt").read_text(encoding="utf-8", errors="replace")
    # done only if the plugin saw the day's data processed; anything else: the day failed, the
    # account goes back to how it was, and the next run retries the day
    ok = f"session {session} done (data processed)" in text and ledger(dep).get("last_session") == session
    error = ""
    if not ok:
        if f"session {session} done (no data within the time limit)" in text:
            error = ("the strategy got no data for this day (no stock subscribed at daily resolution, or a universe "
                     "it couldn't read: `klean update models` and redeploy if its KRX models are old)")
        else:
            match = re.findall(r"(?:ERROR::|Runtime Error:|Exception:)\s*(.+)", text)
            error = (match[-1] if match else f"LEAN exited ({code_}) before the day was processed").strip()[:400]
        shutil.copy2(backup, dep / LEDGER)
    backup.unlink(missing_ok=True)
    book = ledger(dep)
    equity = next((e["equity"] for e in reversed(book.get("equity", [])) if e["session"] == session), None)
    entry = {"session": session, "ok": ok, "seconds": round(time.monotonic() - started, 1), "exit_code": code_,
             "equity": equity, "orders": sum(1 for o in book.get("open_orders", []) if o.get("placed_session") == session),
             "fills": sum(1 for f in book.get("fills", []) if f.get("session") == session),
             **({"error": error} if error else {})}
    record = load(dep)
    record["runs"] = [r for r in record["runs"] if r["session"] != session] + [entry]
    save(dep, record)
    return entry


def run(ws: Workspace, dep: Path, log=print, max_sessions: int = 0, now: bool = False) -> list[dict]:
    """Process every trading day the deployment hasn't seen yet, oldest first; stops at the
    first failure (the next run retries it). A KIS deployment runs only during KRX's pre-open
    auction (08:30-08:59 KST) on a trading day, unless ``now`` (testing a 모의투자 account during
    market hours: market orders then fill at once)."""
    record = load(dep)
    if record["status"] != "running":
        return []
    if is_kis(record):
        from klean import kis
        t = kis.now_kst()
        if not now and not (kis.in_pre_open(t) and is_trading_day(ws, t.date())):
            log(f"klean: live {record['project']}/{dep.name} (KIS-PAPER): orders go out during the pre-open auction, "
                f"08:30-08:59 KST on trading days; it's {t:%a %H:%M} KST: skipped")
            return []
        kis.Kis()                    # checks the KIS-PAPER keys (and says to rename keys from klean 0.0.20)
    ensure_plugin(ws, log)
    done = []
    for session in pending_sessions(ws, dep)[: max_sessions or None]:
        entry = run_session(ws, dep, session, log=log, now=now)
        done.append(entry)
        if not entry["ok"]:
            log(f"klean: live {dep.name}: {session} FAILED: {entry.get('error')}")
            break
    return done


def run_all(ws: Workspace, log=print, now: bool = False) -> list[tuple[str, list[dict]]]:
    """Every running deployment in the workspace (after a data update). KIS deployments outside
    their pre-open window are skipped with a note."""
    out = []
    for project in projects.list_projects(ws):
        for dep in deployments(project):
            if load(dep)["status"] == "running":
                out.append((f"{project.name}/{dep.name}", run(ws, dep, log, now=now)))
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
            "start_cash": start_cash, "cash": book.get("cash"), "holdings": len(book.get("holdings", {})),
            "open_orders": len(book.get("open_orders", []))}


# ---------------------------------------------------------------- for the GUI

def _daily_rows(path: Path) -> list[tuple[str, list[str]]]:
    if not path.exists():
        return []
    with zipfile.ZipFile(path) as z:
        lines = z.read(z.namelist()[0]).decode().splitlines()
    return [(f"{x[:4]}-{x[4:6]}-{x[6:8]}", x.split(",")) for x in lines if len(x) >= 8]


def last_close(ws: Workspace, code: str, session: str) -> float | None:
    """The stock's close on ``session`` or the last trading day before it, in won."""
    rows = [r for d, r in _daily_rows(ws.data / "equity" / "krx" / "daily" / f"{code.lower()}.zip") if d <= session]
    return float(rows[-1][4]) / 10000 if rows else None


def detail(ws: Workspace, dep: Path) -> dict:
    """Everything the Live dashboard shows for one deployment."""
    sm, book, record = summary(ws, dep), ledger(dep), load(dep)
    session = book.get("last_session") or ""
    positions = []
    for code, h in book.get("holdings", {}).items():
        close = last_close(ws, code, session) if session else None
        value = h["quantity"] * close if close is not None else None
        positions.append({"symbol": code, "quantity": h["quantity"], "average_price": h["average_price"],
                          "last": close, "value": value,
                          "pnl": value - h["quantity"] * h["average_price"] if value is not None else None})
    total = sm["equity"] or 1
    for p in positions:
        p["weight"] = (p["value"] or 0) / total * 100
    equity = book.get("equity", [])
    bench = {d: float(r[4]) for d, r in _daily_rows(ws.data / "index" / "krx" / "daily" / "kospi200.zip")}
    first = next((bench[e["session"]] for e in equity if e["session"] in bench), None)
    start_cash = book.get("start_cash") or record["cash"]

    def ts(day: str) -> int:
        return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())

    return {**sm, "positions": sorted(positions, key=lambda p: -(p["value"] or 0)),
            "waiting": book.get("open_orders", []), "fills": list(reversed(book.get("fills", [])))[:500],
            "events": list(reversed(book.get("events", [])))[:200],
            "runs": list(reversed(record.get("runs", []))),
            "equity_curve": [[ts(e["session"]), e["equity"]] for e in equity],
            "benchmark": [[ts(e["session"]), bench[e["session"]] / first * start_cash] for e in equity
                          if first and e["session"] in bench],
            "pending_days": pending_sessions(ws, dep) if record["status"] == "running" else []}


def console_tail(dep: Path, session: str, lines: int = 300) -> list[str]:
    path = dep / "runs" / session / "console.txt"
    if path.parent.parent != dep / "runs" or not path.exists():
        raise KleanError(f"no run for {session}")
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
