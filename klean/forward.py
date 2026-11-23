"""Forward tests: paper trading on daily data (`klean live`, the GUI's Live dashboard).

A forward test freezes a project's code and parameters on the day it starts. After each data
update it runs that frozen code from its start date up to the latest data date, with the same
KRX fees, taxes and slippage as a backtest. LEAN backtests are deterministic, so re-running from
the start gives the same result as trading day by day; the days after the start were unknown
when the code was frozen, so the result is out of sample. No broker, no money.

Folder: ``<project>/live/<id>/`` with ``forward.json`` (settings and a refresh history),
``code/`` (the frozen project files) and ``run/`` (the latest results, a normal LEAN results
folder that every page showing a backtest can show).

The strategy must take its period from the ``start_date`` / ``end_date`` parameters:
``set_period(self, "2011-01-01")`` in Python, ``KrxModels.SetPeriod(this, "2011-01-01")`` in C#
(both in the KRX models; the templates use them).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path

from klean import projects, results
from klean.workspace import KleanError, Workspace

RECORD = "forward.json"
PERIOD_CALL = re.compile(r"\bset_period\s*\(|\bSetPeriod\s*\(")


def live_dir(project: Path) -> Path:
    return project / "live"


def tests(project: Path) -> list[Path]:
    """The project's forward tests, oldest first."""
    d = live_dir(project)
    return sorted(t for t in d.iterdir() if (t / RECORD).exists()) if d.is_dir() else []


def load(test: Path) -> dict:
    return json.loads((test / RECORD).read_text(encoding="utf-8"))


def save(test: Path, record: dict) -> None:
    tmp = test / (RECORD + ".tmp")
    tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(test / RECORD)


def find(project: Path, test_id: str) -> Path:
    test = live_dir(project) / test_id
    if not (test / RECORD).exists() or test.parent != live_dir(project):
        raise KleanError(f"no forward test {test_id!r} in {project.name} (`klean live status {project.name}`)")
    return test


def iso(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}" if len(yyyymmdd) == 8 else yyyymmdd


def uses_period(code: Path) -> bool:
    return any(PERIOD_CALL.search(f.read_text(encoding="utf-8", errors="replace"))
               for f in [*code.glob("*.py"), *code.glob("*.cs")] if f.name not in ("krx_models.py", "KrxModels.cs"))


def start(ws: Workspace, project: Path, name: str = "", parameters: dict[str, str] | None = None,
          start_date: str = "", source_run: str = "") -> Path:
    """Freeze the project's code and create a forward test; returns its folder (not yet run).
    ``start_date`` (YYYY-MM-DD) defaults to the day after the latest data; an earlier one makes
    a *backdated* test (the code has seen those days: it's labeled so)."""
    project = project.resolve()
    language = projects.language_of(project)
    last = results.last_data_date(ws)
    if not last:
        raise KleanError("no KRX data in this workspace: `klean install data` first")
    last_day = dt.date.fromisoformat(iso(last))
    day = dt.date.fromisoformat(start_date) if start_date else last_day + dt.timedelta(days=1)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    test = live_dir(project) / (f"{stamp}_{safe}" if safe else stamp)
    if test.exists():
        raise KleanError(f"{test} already exists")
    code = test / "code"
    test.mkdir(parents=True)
    try:
        results.snapshot_code(project, code)
        if not uses_period(code):
            raise KleanError(
                f"{project.name}'s code sets its own dates, so a forward test can't move them. Replace "
                "set_start_date/set_end_date with set_period(self, \"YYYY-MM-DD\") (Python, from krx_models) "
                "or KrxModels.SetPeriod(this, \"yyyy-MM-dd\") (C#); `klean update models "
                f"{project.name}` first if its krx_models is older")
        params = {str(k): str(v) for k, v in (parameters or {}).items() if k not in ("start_date", "end_date")}
        save(test, {"id": test.name, "name": name or test.name, "project": project.name, "language": language,
                    "parameters": params, "source_run": source_run, "start_date": day.isoformat(),
                    "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "data_last_date_at_start": iso(last), "backdated": day <= last_day,
                    "synthetic_demo_data": results.is_demo_data(ws),
                    "status": "running", "refreshes": []})
    except BaseException:
        shutil.rmtree(test, ignore_errors=True)
        raise
    return test


def refresh(ws: Workspace, test: Path, timeout: float = 0) -> dict:
    """Run the frozen code from the start date to the latest data date. Returns the new history
    entry ({"skipped": reason} when there was nothing to do)."""
    from klean.backtest import backtest
    record = load(test)
    if record["status"] != "running":
        return {"skipped": "stopped"}
    last = iso(results.last_data_date(ws))
    if not last or last < record["start_date"]:
        return {"skipped": f"waiting for data after {record['start_date']} (latest {last or 'none'})"}
    new, old = test / "run.new", test / "run"
    shutil.rmtree(new, ignore_errors=True)
    entry = {"at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "data_last_date": last}
    try:
        backtest(ws, test / "code", {**record["parameters"], "start_date": record["start_date"], "end_date": last},
                 output=new, backtest_name=f"forward {record['name']}", timeout=timeout)
        curve = results.equity_curve(new)
        first = dt.datetime.fromtimestamp(curve[0][0], dt.timezone.utc).date().isoformat() if curve else ""
        if first and first < (dt.date.fromisoformat(record["start_date"]) - dt.timedelta(days=7)).isoformat():
            raise KleanError(f"the run started on {first}, not {record['start_date']}: the code doesn't take its "
                             "period from set_period / KrxModels.SetPeriod")
        shutil.rmtree(old, ignore_errors=True)
        new.rename(old)
        stats = results.statistics(old)
        entry.update(ok=True, end_equity=stats.get("End Equity", ""), net_profit=stats.get("Net Profit", ""))
    except KleanError as e:
        entry.update(ok=False, error=str(e).splitlines()[0])
        if new.exists():                      # keep the failed run's files for `klean logs`
            failed = test / "run.failed"
            shutil.rmtree(failed, ignore_errors=True)
            new.rename(failed)
    record = load(test)                       # (stopped meanwhile? keep that)
    record["refreshes"] = [*record["refreshes"], entry][-200:]
    save(test, record)
    return entry


def stop(test: Path) -> dict:
    record = load(test)
    if record["status"] != "stopped":
        record.update(status="stopped", stopped_utc=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        save(test, record)
    return record


def summary(ws: Workspace, test: Path) -> dict:
    """What a list shows: the record plus the state and the latest results."""
    record = load(test)
    last = record["refreshes"][-1] if record["refreshes"] else None
    run = test / "run"
    stats = {}
    if run.is_dir():
        try:
            stats = results.statistics(run)
        except KleanError:
            stats = {}
    if record["status"] == "stopped":
        state = "stopped"
    elif last and not last.get("ok"):
        state = "failed"
    elif not run.is_dir():
        state = "waiting for data"
    else:
        state = "running"
    return {**{k: v for k, v in record.items() if k != "refreshes"}, "state": state,
            "refreshes": len(record["refreshes"]), "last_refresh": last,
            "ref": run.relative_to(ws.root).as_posix() if run.is_dir() else "",
            "stats": {k: stats.get(k, "") for k in ("Compounding Annual Return", "Drawdown", "Sharpe Ratio",
                                                     "Net Profit", "End Equity", "Total Orders")}}


def refresh_all(ws: Workspace, log=print) -> list[tuple[str, dict]]:
    """Refresh every running forward test in the workspace (after a data update)."""
    done = []
    for project in projects.list_projects(ws):
        for test in tests(project):
            if load(test)["status"] != "running":
                continue
            entry = refresh(ws, test)
            label = f"{project.name}/{test.name}"
            if "skipped" in entry:
                log(f"klean: forward test {label}: {entry['skipped']}")
            elif entry["ok"]:
                log(f"klean: forward test {label}: to {entry['data_last_date']}, end equity {entry['end_equity']}")
            else:
                log(f"klean: forward test {label} FAILED: {entry['error']}")
            done.append((label, entry))
    return done
