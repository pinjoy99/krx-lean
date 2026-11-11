"""Extra LEAN inputs built from the raw KRX data.

* ``lean/index/krx/daily/{ticker}.zip`` — the main indices (``kospi``, ``kospi200``, ``kosdaq``,
  ``kosdaq150``, ``krx300``) in LEAN's index format (``yyyyMMdd 00:00,o,h,l,c,volume``, levels
  unscaled), for ``AddIndex("KOSPI200", Resolution.Daily, Market.KRX)`` / ``SetBenchmark``.
  LEAN already ships ``Index-krx-[*]`` market hours and symbol properties.
* ``lean/equity/krx/universe/{yyyyMMdd}.zip`` — one file per trading day with every security
  that traded: ``code,market,close,volume,value,market_cap,shares`` (raw KRW, as KRX reports
  them), for a LEAN custom universe (e.g. top N by market cap). Only missing or outdated days are
  rewritten.
* ``lean/equity/krx/securities.csv`` — copy of ``securities.csv`` so LEAN-side models can look up
  each code's market (KOSPI / KOSDAQ / KONEX / ETF) for taxes and tick sizes.
"""

from __future__ import annotations

import csv
import gzip
import io
import logging
import os
import shutil
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

INDEX_TICKERS = {"KOSPI": "kospi", "KOSPI200": "kospi200", "KOSDAQ": "kosdaq",
                 "KOSDAQ150": "kosdaq150", "KRX300": "krx300"}
UNIVERSE_COLUMNS = ["code", "market", "close", "volume", "value", "market_cap", "shares"]


def _zip_one(path: Path, name: str, text: str) -> bool:
    """Write a one-member zip, reproducibly: the member has a fixed timestamp, so the same text
    gives the same bytes, and an unchanged file is left alone (its modification time stays, and
    `lean-install` skips it). Returns True if the file was written."""
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(info, text)
    data = buf.getvalue()
    if path.exists() and path.stat().st_size == len(data) and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return True


def build_lean_indices(root: Path, lean_root: Path, market: str = "krx") -> int:
    n = 0
    for name, ticker in INDEX_TICKERS.items():
        src = root / "index" / f"{name}.csv"
        if not src.exists():
            continue
        lines = []
        with open(src, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                lines.append(f"{r['date']} 00:00,{r['open']},{r['high']},{r['low']},{r['close']},{r['volume'] or 0}")
        _zip_one(lean_root / "index" / market / "daily" / f"{ticker}.zip", f"{ticker}.csv", "\n".join(lines) + "\n")
        n += 1
    return n


def _num(v: str) -> str:
    v = (v or "").replace(",", "").strip()
    return "" if v in ("", "-") else v


def build_universe(root: Path, lean_root: Path, market: str = "krx") -> int:
    """Write universe files for trading days whose raw files are newer than the output."""
    by_date: dict[str, list[Path]] = {}
    for path in (root / "raw" / "krx").glob("*/*/*.csv.gz"):
        by_date.setdefault(path.name[:8], []).append(path)
    out_dir = lean_root / "equity" / market / "universe"
    written = 0
    for date, paths in sorted(by_date.items()):
        out = out_dir / f"{date}.zip"
        if out.exists() and out.stat().st_mtime >= max(p.stat().st_mtime for p in paths):
            continue
        rows = []
        for path in sorted(paths):
            board = path.parent.parent.name
            with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    close = _num(r.get("TDD_CLSPRC", ""))
                    if not close or close == "0":
                        continue
                    rows.append([r["ISU_CD"], board, close, _num(r.get("ACC_TRDVOL", "")),
                                 _num(r.get("ACC_TRDVAL", "")), _num(r.get("MKTCAP", "")), _num(r.get("LIST_SHRS", ""))])
        if not rows:
            continue  # non-trading day
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(UNIVERSE_COLUMNS)
        w.writerows(sorted(rows))
        _zip_one(out, f"{date}.csv", buf.getvalue())
        written += 1
    return written


def build_lean_extras(root: Path, market: str = "krx") -> dict:
    lean_root = root / "lean"
    stats = {"indices": build_lean_indices(root, lean_root, market),
             "universe_days_written": build_universe(root, lean_root, market)}
    if (root / "securities.csv").exists():
        dst = lean_root / "equity" / market / "securities.csv"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / "securities.csv", dst)
    log.info("build: LEAN extras %s", stats)
    return stats
