"""`klean schedule install | status | remove`: the daily jobs of a workspace, in the user's crontab.

- **data**: `klean update data` once a day, after KRX has published the previous trading day
  (21:30 KST); it also runs the deployments on klean's paper broker.
- **kis**: `klean live run` in KRX's pre-open auction (08:35 KST, Monday to Friday; KRX holidays
  skip themselves): KIS-PAPER deployments trade only then.

The times are written in the computer's local time zone. Where it has daylight saving time, the
pre-open job gets both local hours (one of them lands outside the window and skips itself). Lines
klean writes end with "# klean-schedule:<job>:<workspace>"; other lines are never changed, and a job
already scheduled by hand (e.g. a script that runs `klean update data`) is left as it is.
"""

from __future__ import annotations

import datetime as dt
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from klean.workspace import KleanError, Workspace, dotnet

KST = dt.timezone(dt.timedelta(hours=9))
MARK = "# klean-schedule:"
JOBS = {
    # job: (KST time, KST weekdays (Mon=0) or None for every day, what it runs, what it's for)
    "data": (dt.time(21, 30), None, "update data", "the day's KRX data, then paper-broker deployments"),
    "kis": (dt.time(8, 35), (0, 1, 2, 3, 4), "live run", "KIS-PAPER deployments, in KRX's pre-open auction"),
}
# hand-made lines that already do a job
HAND_MADE = {"data": ("klean update data", "klean update all", "krx-update"),
             "kis": ("klean live run", "klean-kis-paper")}


# ---------------------------------------------------------------- the crontab

def read_crontab() -> str:
    if not shutil.which("crontab"):
        raise KleanError("no `crontab` command: install cron (Ubuntu/WSL: `sudo apt install -y cron`), "
                         "or schedule the jobs another way (`klean schedule status` shows the commands)")
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if r.returncode and "no crontab" in (r.stderr or "").lower():
        return ""
    if r.returncode:
        raise KleanError(f"crontab -l: {r.stderr.strip()}")
    return r.stdout


def write_crontab(text: str) -> None:
    r = subprocess.run(["crontab", "-"], input=text, capture_output=True, text=True)
    if r.returncode:
        raise KleanError(f"crontab: {r.stderr.strip()}")


# ---------------------------------------------------------------- times

def local_slots(kst_time: dt.time, weekdays: tuple[int, ...] | None, year: int | None = None) -> list[str]:
    """Cron time fields (minute hour * * weekdays) in the local time zone for a KST time, covering
    standard and daylight saving time (one line per distinct minute and weekday set)."""
    year = year or dt.date.today().year
    slots: dict[tuple[int, str], set[int]] = {}
    for month in (1, 7):                                  # winter and summer
        monday = dt.date(year, month, 15)
        monday -= dt.timedelta(days=monday.weekday())
        days = weekdays if weekdays is not None else range(7)
        local_days, minute, hour = set(), None, None
        for wd in days:
            t = dt.datetime.combine(monday + dt.timedelta(days=wd), kst_time, tzinfo=KST)
            local = dt.datetime.fromtimestamp(t.timestamp())   # the computer's time zone, with its DST rules
            minute, hour = local.minute, local.hour
            local_days.add((local.weekday() + 1) % 7)       # cron: Sunday = 0
        dow = "*" if weekdays is None else cron_days(local_days)
        slots.setdefault((minute, dow), set()).add(hour)
    return [f"{m} {','.join(str(h) for h in sorted(hs))} * * {dow}" for (m, dow), hs in sorted(slots.items())]


def cron_days(days: set[int]) -> str:
    """{1,2,3,4,5} -> "1-5"; {0,1,2,3,4} -> "0-4"; anything else as a list."""
    s = sorted(days)
    if len(s) > 1 and s == list(range(s[0], s[-1] + 1)):
        return f"{s[0]}-{s[-1]}"
    return ",".join(str(d) for d in s)


def next_run(job: str, now: dt.datetime | None = None) -> dt.datetime:
    """The next time (KST) the job is due."""
    kst_time, weekdays, _, _ = JOBS[job]
    now = (now or dt.datetime.now(KST)).astimezone(KST)
    day = now.date()
    for _ in range(8):
        t = dt.datetime.combine(day, kst_time, tzinfo=KST)
        if t > now and (weekdays is None or day.weekday() in weekdays):
            return t
        day += dt.timedelta(days=1)
    return t


# ---------------------------------------------------------------- lines

def log_path(ws: Workspace, job: str) -> Path:
    return Path(ws.root) / ".klean" / "logs" / f"schedule-{job}.log"


def command(ws: Workspace, job: str) -> str:
    """The shell command a job runs: this klean (its Python), .NET found, output to the job's log."""
    try:
        dotnet_dir = str(Path(dotnet()).resolve().parent)
    except KleanError:
        dotnet_dir = str(Path.home() / ".dotnet")
    q = shlex.quote
    log = log_path(ws, job)
    run = f"{q(sys.executable)} -m klean {JOBS[job][2]}"
    return (f"cd {q(str(ws.root))} && {{ echo \"=== $(date)\"; DOTNET_ROOT={q(dotnet_dir)} "
            f"PATH={q(dotnet_dir)}:\"$PATH\" {run}; }} >> {q(str(log))} 2>&1")


def lines_for(ws: Workspace, job: str) -> list[str]:
    kst_time, weekdays, _, _ = JOBS[job]
    return [f"{slot} {command(ws, job)}  {MARK}{job}:{ws.root}" for slot in local_slots(kst_time, weekdays)]


def managed(text: str, ws: Workspace, job: str | None = None) -> list[str]:
    tag = f"{MARK}{job}:{ws.root}" if job else None
    return [ln for ln in text.splitlines()
            if MARK in ln and ln.rstrip().endswith(f":{ws.root}") and (tag is None or ln.rstrip().endswith(tag))]


def hand_made(text: str, job: str) -> list[str]:
    """Lines not written by klean that already do this job."""
    return [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#") and MARK not in ln
            and any(k in ln for k in HAND_MADE[job])]


def scheduled(ws: Workspace, job: str, text: str | None = None) -> bool:
    text = read_crontab() if text is None else text
    return bool(managed(text, ws, job) or hand_made(text, job))


def kis_hint(ws: Workspace) -> str:
    """After a KIS-PAPER deploy: "" if a pre-open `klean live run` is scheduled, else what to do
    (without one, the deployment never trades: no other run happens in the pre-open window)."""
    try:
        if scheduled(ws, "kis"):
            return ""
        how = ""
    except KleanError as e:
        how = f" ({e})"
    kst_time, weekdays, _, _ = JOBS["kis"]
    slots = "; ".join(local_slots(kst_time, weekdays))
    nxt = next_run("kis")
    text = (f"No `klean live run` is scheduled for KRX's pre-open auction{how}: this deployment trades only when "
            f"one runs between 08:30 and 08:59 KST (next: {nxt:%a %H:%M} KST = {nxt.astimezone():%a %H:%M} here). "
            f"Run `klean schedule install`, or add to your crontab: {slots} cd {ws.root} && klean live run")
    if "microsoft" in platform.release().lower():
        text += " (WSL: cron runs only while WSL is up; Windows Task Scheduler is more reliable)"
    return text


# ---------------------------------------------------------------- commands

def install(ws: Workspace, jobs: tuple[str, ...] = ("data", "kis"), log=print) -> list[str]:
    """Add klean's lines for the jobs that aren't scheduled yet; replace klean's own lines (times
    or paths may have changed). Returns the lines added."""
    text = read_crontab()
    keep = [ln for ln in text.splitlines() if not any(ln in managed(text, ws, j) for j in jobs)]
    added = []
    for job in jobs:
        hand = hand_made(text, job)
        if hand:
            log(f"klean: {job}: already scheduled by hand, left as it is:\n    {hand[0]}")
            continue
        added += lines_for(ws, job)
    if added or len(keep) != len(text.splitlines()):
        backup = Path.home() / ".klean" / f"crontab.{dt.datetime.now():%Y%m%d-%H%M%S}.bak"
        backup.parent.mkdir(exist_ok=True)
        backup.write_text(text, encoding="utf-8")
        log_path(ws, "data").parent.mkdir(parents=True, exist_ok=True)
        new = "\n".join(keep + added).strip("\n") + "\n"
        write_crontab(new)
        log(f"klean: crontab updated (the previous one is saved as {backup})")
    for ln in added:
        log(f"  + {ln.split(' cd ')[0]}  {JOBS[ln.rsplit(MARK, 1)[1].split(':')[0]][3]}")
    log(cron_service_note())
    return added


def remove(ws: Workspace, log=print) -> int:
    text = read_crontab()
    mine = managed(text, ws)
    if mine:
        write_crontab("\n".join(ln for ln in text.splitlines() if ln not in mine).strip("\n") + "\n")
    log(f"klean: removed {len(mine)} line(s) for {ws.root}" if mine else f"klean: no klean lines for {ws.root}")
    return len(mine)


def status(ws: Workspace, log=print) -> dict:
    text = read_crontab()
    out = {}
    for job, (_, _, _, what) in JOBS.items():
        mine, hand = managed(text, ws, job), hand_made(text, job)
        nxt = next_run(job)
        log(f"{job}: {what}")
        if mine:
            for ln in mine:
                log(f"  klean's line: {ln.split(' cd ')[0]}")
        for ln in hand:
            log(f"  your line:    {ln}")
        if not (mine or hand):
            log("  NOT SCHEDULED: `klean schedule install` adds it")
        log(f"  next due: {nxt:%a %Y-%m-%d %H:%M} KST = {nxt.astimezone():%a %H:%M} here")
        last = last_log(log_path(ws, job))
        if last:
            log(f"  last run (klean's log {log_path(ws, job)}): {last}")
        out[job] = {"managed": mine, "hand_made": hand, "next": nxt.isoformat(), "last": last}
    log(cron_service_note())
    return out


def last_log(path: Path) -> str:
    """The last "=== <date>" line of a job's log, and its last line."""
    if not path.exists():
        return ""
    lines = [ln for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    starts = [ln for ln in lines if ln.startswith("=== ")]
    return f"{starts[-1][4:]} … {lines[-1][:160]}" if starts else ""


def cron_service_note() -> str:
    """Is something going to run the crontab? (cron must be running; under WSL, WSL too)."""
    running = any(subprocess.run(["pgrep", "-x", name], capture_output=True).returncode == 0
                  for name in ("cron", "crond")) if shutil.which("pgrep") else None
    if platform.system() == "Darwin":
        return "cron: macOS runs the crontab itself (while the Mac is awake)"
    note = ("cron: running" if running else
            "cron: NOT RUNNING. Start it: `sudo service cron start` (or `sudo systemctl enable --now cron`)"
            if running is False else "cron: couldn't check whether it runs")
    if "microsoft" in platform.release().lower():
        note += ("\n  WSL: cron runs only while WSL is up (it stops soon after its last terminal closes). "
                 "To be sure, use Windows Task Scheduler instead, which starts WSL itself (docs: 6. Daily update)")
    return note


if __name__ == "__main__":                 # quick look: the lines for this time zone
    print("\n".join(f"{job}: {s}" for job, (t, d, _, _) in JOBS.items() for s in local_slots(t, d)))
    sys.exit(0)
