"""Locks between klean processes (the GUI, cron jobs, the command line), with ``flock`` on a lock
file: Linux, WSL2 and macOS. The operating system releases a lock when its process ends, even
after a crash or ``kill -9``, so a lock is never left behind.

    with locks.hold(path, "installing data"):            # wait for it
        ...
    with locks.hold(path, "trading", wait=False):        # or give up at once: locks.Busy
        ...
    with locks.hold(path, "a live day", shared=True):    # many shared holders, or one exclusive

The lock file records who holds it (pid, what, since when) so that a process that waits or gives
up can say what it's waiting for. Some file systems don't support ``flock`` (possibly WSL's
/mnt/c drives): klean checks once per folder and warns, then runs without the lock there.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import errno
import fcntl
import json
import os
import sys
import threading
import time
from pathlib import Path

from klean.workspace import KleanError


class Busy(KleanError):
    """The lock is held by another process (``holder`` describes it) and we didn't wait."""

    def __init__(self, message: str, holder: dict):
        super().__init__(message)
        self.holder = holder


_checked: dict[str, bool] = {}
UNSUPPORTED = {errno.ENOLCK, errno.EOPNOTSUPP, errno.ENOSYS, errno.EINVAL}


def works_in(folder: Path) -> bool:
    """Does flock work in this folder? Two handles on one file must exclude each other."""
    key = str(folder.resolve())
    if key not in _checked:
        # this process's own probe file: another klean process probing the folder at the same
        # moment must not look like "locks don't work"
        probe = folder / f".klean-lock-probe-{os.getpid()}-{threading.get_ident()}"
        ok = True
        try:
            with open(probe, "a+") as a, open(probe, "a+") as b:
                fcntl.flock(a, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    fcntl.flock(b, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    ok = False                      # both got it: flock does nothing here
                except OSError as e:
                    if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                        ok = False                  # an error other than "held": not supported
        except OSError as e:
            ok = e.errno not in UNSUPPORTED         # no locks on this file system; else (e.g. read-only) leave it
            if ok:
                print(f"klean: warning: can't check file locks in {folder}: {e}", file=sys.stderr)
        finally:
            with contextlib.suppress(OSError):
                probe.unlink()
        if not ok:
            print(f"klean: warning: file locks don't work in {folder}; klean can't keep two of its processes "
                  "apart there. Keep the workspace in your Linux home folder (~), not on /mnt/c.", file=sys.stderr)
        _checked[key] = ok
    return _checked[key]


def describe(holder: dict) -> str:
    if not holder:
        return "another klean process"
    since = holder.get("since", "")
    return f"pid {holder.get('pid', '?')} ({holder.get('what', 'klean')}, since {since[11:19] or since})"


def holder_of(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return {}


@contextlib.contextmanager
def hold(path: Path, what: str, wait: bool = True, timeout: float | None = None, shared: bool = False,
         on_wait=None):
    """Hold the lock at ``path`` for the ``with`` block. ``wait=False`` raises Busy at once if
    another process holds it; ``timeout`` (seconds) raises Busy after waiting that long.
    ``on_wait(holder)`` is called once if we have to wait."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not works_in(path.parent):
        yield
        return
    f = open(path, "a+", encoding="utf-8")
    try:
        mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
        try:
            fcntl.flock(f, mode | fcntl.LOCK_NB)
        except OSError:
            holder = holder_of(path)
            if not wait:
                raise Busy(f"{what}: busy, {describe(holder)} holds it", holder) from None
            if on_wait:
                on_wait(holder)
            deadline = None if timeout is None else time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(f, mode | fcntl.LOCK_NB)
                    break
                except OSError:
                    if deadline is not None and time.monotonic() > deadline:
                        raise Busy(f"{what}: still busy after {timeout:.0f} s, {describe(holder_of(path))} "
                                   "holds it", holder_of(path)) from None
                    time.sleep(0.2)
        if not shared:          # who holds it, for the messages of those who wait (shared holders don't write)
            f.seek(0)
            f.truncate()
            f.write(json.dumps({"pid": os.getpid(), "what": what,
                                "since": dt.datetime.now().isoformat(timespec="seconds")}))
            f.flush()
        try:
            yield
        finally:
            if not shared:
                with contextlib.suppress(OSError):
                    f.seek(0)
                    f.truncate()
                    f.flush()
            fcntl.flock(f, fcntl.LOCK_UN)
    finally:
        f.close()


def lock_dir(ws_root: Path) -> Path:
    return Path(ws_root) / ".klean" / "locks"


def data_lock(ws_root: Path) -> Path:
    """The workspace's data: exclusive while installing it, shared by each live trading day."""
    return lock_dir(ws_root) / "data.lock"


def replace_file(src: Path, dst: Path) -> None:
    """Copy ``src`` over ``dst`` in one step: a reader sees the old file or the new one, never part
    of one (copy to a temporary name in the same folder, then rename). Keeps ``src``'s times."""
    import shutil
    tmp = dst.with_name(f".{dst.name}.klean-tmp-{os.getpid()}")
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()
