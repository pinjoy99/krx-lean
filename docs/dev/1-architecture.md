# 1. Architecture

```
KRX Open API ─┐                                                  ┌─▶ C# algorithms
data.go.kr ───┼─▶ krx_lean: raw/ ─▶ build ─▶ lean/ ─▶ lean-install ─▶ LEAN (source build, .NET 10)
aikstockdata ─┤        verify → reports/ (cross-checks only)     └─▶ Python algorithms (pythonnet, 3.11)
Yahoo daily ──┘                                  ▲
                      klean: workspace, projects, runs, optimize, report, research notebooks, GUI
```

Three parts, connected only through files:

| Part | Code | Output / interface |
|---|---|---|
| **Data pipeline** | `krx_lean/` | `<root>/raw/` (downloads, lossless) → `<root>/lean/` (LEAN's data layout), CSVs for research, `reports/` |
| **KRX models** | `examples/KrxModels.cs`, `examples/python/krx_models.py` | fee/tax, tick size, universe and benchmark types used inside algorithms; read `equity/krx/securities.csv`, `universe/`, `index/krx/` from LEAN's data folder |
| **klean** | `klean/` | workspaces (`klean.json`, `data/`), projects, run folders; drives LEAN's launchers |

LEAN itself is not modified: it is cloned at a pinned commit and built from source. The KRX
market is added through LEAN's data files: an `Equity-krx-[*]` entry in
`market-hours-database.json` and a `krx` line in `symbol-properties-database.csv`, both written
by `lean_install.py`.

## Repository layout

```
krx_lean/            data pipeline (command `krx-lean`)
  cli.py             commands
  client.py          HTTP client (pacing, retries)
  krx_api.py         KRX Open API: daily prices, indices, security master
  dividends.py       data.go.kr dividends
  rights.py          data.go.kr corporate-action schedules
  build.py           raw → ohlcv/, lean/, securities.csv, …
  factors.py         split and price factors
  lean_extras.py     universe files, index files
  lean_install.py    copy into a LEAN data folder, KRX market hours / symbol properties, lean-package
  verify.py          cross-checks against aikstockdata and Yahoo
  demo.py            synthetic demo data in the raw download formats
  scraper.py         aikstockdata (cross-check source)
  yahoo.py           Yahoo daily bars via yfinance (cross-check source; optional dependency)
klean/               workspace tool (command `klean`; modules in 6. klean internals)
examples/            KRX models (C#, Python) and example algorithms; klean copies them into projects
tests/               pipeline unit tests; tests/klean/ klean unit tests
docs/user/, docs/dev/
```

## Design principles

- **Raw is the only state.** Downloads are kept as received; every output is rebuilt from `raw/`,
  so fixing a rule never needs a re-download, and the same raw files + the same krx-lean commit
  give the same LEAN data.
- **One source per fact.** Daily bars come only from the KRX Open API; aikstockdata and Yahoo
  only cross-check them. Dividends come only from data.go.kr.
- **C# and Python models are equivalent.** Every change is made in both and checked with a
  parity run (identical to the won).
- **Local only.** No cloud services, no Docker, no QuantConnect account; LEAN's own programs
  (`Launcher`, `Report`, the research `start.py`) do the work.
- **Scope:** KOSPI and ETF, daily. KOSDAQ/KONEX code paths exist but aren't downloaded or verified.
