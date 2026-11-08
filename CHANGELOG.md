# Changelog

## 0.0.3 — 2026-11-08

- **`klean research PROJECT`**: JupyterLab with LEAN's `QuantBook` on the workspace's data, like
  `lean research` without Docker. Uses LEAN's own `start.py` from the source build; installs
  JupyterLab 4.5.1, ipykernel, clr-loader 0.2.9 and matplotlib into the Python 3.11 environment on
  first use; writes a starter `research.ipynb` (history, a moving average, the stock against the
  KOSPI 200) if the project has none; `--execute` runs a notebook without a browser. The
  project's `krx_models.py` is importable (C# projects get a copy on the path). LEAN's config is
  pinned to klean's file, so a project's own `config.json` isn't read; the object store is
  `<workspace>/storage/` (now kept out of run code snapshots).
- Checked on the synthetic demo data: the starter notebook runs headless (`--execute`) and in
  JupyterLab in a browser, for a Python and a C# project. Real-data notebooks use the same code
  path with the real data folder.
- Docs: users 5-tools "Research notebooks", demo page, troubleshooting; developers 6-klean
  "Research", roadmap; beginner page.

## 0.0.2 — 2026-11-05

Fixes from the first users-track test (a new user following the docs on Ubuntu 24.04).

- **Failed backtests are reported as failed.** LEAN writes a summary even when the algorithm
  throws (e.g. in `initialize`); klean now reads its status: `backtest` prints
  `backtest FAILED` with LEAN's error and exits 1, the manifest records `ok: false` and the
  error, `optimize` ranks such runs as failed, `report` refuses them, `logs` and the GUI show
  the error. The pythonnet `GIL` message at exit gets a one-line explanation.
- **Synthetic demo data** for trying krx-lean without API keys: `klean data install --demo`
  (or `krx-lean demo`) generates made-up KOSPI-like stocks, ETFs and KOSPI / KOSPI 200 indices
  in the raw download formats and runs the real build. Clearly marked everywhere (codes `D…`,
  names, marker files, banners in the CLI, reports and GUI, run manifests); demo and real data
  can't share a workspace. Doubles as test data. New page: docs/user/demo.md.
- **Benchmark data:** `krx_benchmark` / `KrxIndex.Benchmark` stop with a message saying how to
  get the index data; `klean doctor` checks for the KOSPI 200 index.
- **Network errors** during downloads stop with "re-run the same command to resume" instead of
  a traceback.
- `buy-hold` template: the stock is the parameter `code` (default Samsung, or the demo stock in
  a demo workspace); it buys only once the stock has data.
- Docs: no more "private repository" notes; realistic install times; `/tmp` space for the .NET
  installer; failure output; `--sample`'s limits; new troubleshooting rows.

Results on real data are unchanged (top-market-cap C# = Python, identical to 0.0.1).

## 0.0.1 — 2026-11-02 (first release)

First release as krx-lean (previously developed as qc-krx). Tested with LEAN commit
`80e7843f645673bcbeaab963049f76f20f6785e1` and .NET 10 on Ubuntu (native and WSL2).

- **Data pipeline** (`krx-lean`): KOSPI and ETF daily prices and the KOSPI index family from the
  KRX Open API (2010 onward), dividends and corporate-action dates from data.go.kr; LEAN daily,
  factor, map and universe files; KRX market hours and symbol properties; cross-checks against
  aikstockdata and Yahoo (optional `[crosscheck]` extra). `all` now includes dividends when
  `DATA_GO_KR_KEY` is set.
- **KRX models** in C# and Python (identical results): sell-side tax by settlement date,
  commission, tick sizes, daily universe, KOSPI / KOSPI 200 benchmark.
- **klean**: install LEAN and Python 3.11 (via uv), workspaces, project templates, backtests with
  run manifest and code snapshot, compare, logs, grid optimization, LEAN reports (HTML, PDF),
  local GUI. Under WSL2 the GUI opens the Windows browser through `wslview`.
- Strictly local: no Colab, Google Drive or Docker paths.
