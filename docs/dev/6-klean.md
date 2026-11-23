# 6. klean internals

klean is the local part of the LEAN CLI's workflow, rebuilt on a LEAN source build: standard
library only, no Docker, no account. Projects keep the LEAN CLI's layout, so a Python project
also runs under `lean backtest`.

| Module | Does |
|---|---|
| `workspace.py` | `klean.json` (load/save, found upwards from the current folder), tested LEAN commit, Python package pins, `dotnet` and libpython lookup, `doctor` checks |
| `cli.py` | commands; the `<verb> <noun>` commands (`install lean/python/data` (incl. `--demo`), `update data/lean/models/klean/all`, `status …`, `create-project` / `delete-project`) plus the old names as hidden aliases; `init`, `config` |
| `projects.py` | templates (Python, C#), algorithm class detection, `.csproj` (references the launcher DLLs; excludes `backtests/**`, `optimizations/**`) |
| `backtest.py` | `prepare` (py_compile + requirements, or `dotnet build`), `run_once` (code snapshot, per-run config, launcher, manifest), `backtest` |
| `results.py` | finding runs, statistics, equity curves, `compare`, logs, source files and the code snapshot, `status data` |
| `optimize.py` | grid search |
| `report.py` | LEAN's Report |
| `research.py` | Jupyter with LEAN's QuantBook |
| `kis.py`, `plugin/KisClient.cs`, `plugin/KisPaperBrokerage.cs` | KIS-PAPER: the Korea Investment (KIS) 모의투자 Open API only (`openapivts…:29443`; no real-trading server; keys `KIS_PAPER_APP_KEY`, `KIS_PAPER_APP_SECRET`, `KIS_PAPER_ACCOUNT`): tokens (cached, shared by Python and C#), balance, cash orders (VTTC0012U buy, VTTC0011U sell), cancel (VTTC0013U), daily fills (VTTC0081R), daily prices (FHKST03010100); `KisPaperBrokerage` sends orders in the pre-open auction, reads fills on the next run; the data queue asks KIS for day bars the KRX files don't have (`krx-kis-prices`). `tests/fake_kis.py` simulates the API for tests |
| `live.py`, `plugin/` | live paper trading: deployments (`<project>/live/<id>/`: frozen `code/`, `ledger.json`, `runs/<day>/`), one LEAN live-mode process per trading day with klean's plugin (`QuantConnect.Krx.dll`, built into the LEAN build by `ensure_plugin`): `KrxDailyDataQueue` serves the session day's bars, `KrxPaperBrokerage` fills the previous day's orders at the open before LEAN reads the account, records new orders, and stops the run when it's quiet; `KRX_SESSION_DATE` tells the universe reader which day's file to read |
| `gui.py`, `static/` | local web page: `index.html` (shell), `app.css`, `js/main.js` (router), `js/pages/*.js` (one module per dashboard: workspace, research, backtest, live; the backtest dashboard's right column draws `run.js`, `optimization.js` or `compare.js`), `js/chart.js` (uPlot charts), `js/util.js`; `vendor/uplot/` (MIT, copied in; no CDN, no npm build) |

## A run

1. `prepare`: Python — `py_compile` every project `.py` (outside output folders) and
   `pip install -r requirements.txt` into the 3.11 env; C# — `dotnet build` with
   `-p:LeanBin=<launcher dir>` into `<project>/bin/<config>/`.
2. `run_once`: copy the project's source files into `<run>/code/` (excluding `backtests/`,
   `optimizations/`, `bin/`, `obj/`, `__pycache__/`, `storage/`, hidden folders,
   `.ipynb_checkpoints/`, files > 10 MB); write `<run>/config.json` = LEAN's `Launcher/config.json` (comments stripped) with
   `parameters` emptied, plus the workspace's `lean_config` and `--extra-config`; run the
   launcher with `--config`, `--data-folder <workspace>/data/`, `--results-destination-folder`,
   `--parameters`; console to `console.txt`.
3. `manifest.json`: klean version, project, language, algorithm, parameters, LEAN config,
   build config, times, exit code, `krx_lean_commit` and `lean_commit` (`-dirty` with local
   changes), the data's last date, Python env, host, sha256 of every source file, where the code
   snapshot is.
4. Success is decided by `results.run_error`: the run failed if there's no `*-summary.json`, or
   its `state.RuntimeError` is set, or `state.Status` isn't `Completed`. LEAN writes a summary
   (with empty statistics) even when the algorithm throws in `initialize`, so the summary's
   existence alone means nothing. The exit code isn't used: Python runs often abort with
   pythonnet's `GIL must always be released` after the results are written (exit −6); klean
   notes it. A failed run: `backtest` raises with the error and the console tail (exit 1); the
   manifest has `ok: false` and `error`; `optimize` ranks it as failed; `report` refuses it;
   `logs` and the GUI show the error.
   `--timeout SECONDS` kills LEAN after that long; the run fails with `timed out after …`
   (recorded in the manifest, which `run_error` reads first). Run folders are created with
   `unique_dir` (`…-2`, `-3` if two runs start in the same second).
   While LEAN runs, the run folder holds `klean-running.pid` (`results.is_running` checks the
   process is alive): `logs` and the GUI say "running" instead of "failed". `backtest --detach`
   creates the folder, starts `python -m klean backtest … --output <folder>` as its own session
   with output to `klean-detached.log`, and returns. Foreground runs poll the process every
   10 s (elapsed time on a terminal, the `--timeout` deadline, and killing LEAN on Ctrl+C).
5. Demo data (`SYNTHETIC-DEMO-DATA.txt` in `data/equity/krx`): banners in `backtest`,
   `optimize`, `compare`, `status data`, `doctor`; `"synthetic_demo_data": true` in the
   manifest; report title and description; a GUI banner and badges; the `buy-hold` template's
   default stock becomes `D00010`.

## Models copies and `klean update data`

Each project has its own copy of the models (copied by `create-project`), so a project stays
reproducible; the cost is drift after krx-lean is updated. `projects.models_state` compares the
copy byte for byte with `examples/`: `klean backtest` prints a note and records `krx_models` in
the manifest, `doctor` and the GUI show an informational row (never a failure: an edited copy is
legitimate), `klean update models` replaces the copy and keeps the old one as `*.bak`.

`klean update data` = `krx_lean.cli.main(["--root", R, "all"])` in-process, then `install_data`.
`R` is `data_root` in `klean.json`, saved by `klean install data --root`. Keys not in the
environment are read from `--env-file` (default `~/.config/krx-lean.env`); values are never
printed. Refused in a demo workspace.

## Optimize

LEAN's `Optimizer.Launcher` starts each backtest with only results folder, ids, parameters and
algorithm options: no `--data-folder` and no `--config`, so its runs would read LEAN's own
`Data/`. klean therefore compiles once and runs the grid itself in a thread pool, each
combination an ordinary `run_once` into `optimizations/<opt>/<NNN>_k=v/` (sharing
`optimizations/<opt>/code/`). Parameter values use `Decimal` (no float drift). Ranking: runs
meeting the constraints by target, then runs failing them, then failed runs. Grid only (no Euler).

## Report

Builds `Report/` on first use and installs `matplotlib==3.8.4` into the 3.11 env. LEAN's
`Report` accepts only some settings as arguments and reads `template.html`, `css/` and
`ReportCharts.py` from the current folder, so klean runs it in a temporary folder with copies of
those and a generated `config.json`. Known harmless log line: an `InteractiveBrokersFeeModel():
unexpected equity Market krx` error at the end of the order replay (its replay algorithm uses the
default brokerage model); the portfolios are computed before it. PDF: wkhtmltopdf, else headless
Chromium with `@page { size: 1200px 1698px }` added to a temporary copy (one PDF page per report
page).

## Research

LEAN's build already has the research parts: `QuantConnect.Research.dll` and `start.py` in
`Launcher/bin/Release`. `start.py` loads .NET into Python (clr-loader + LEAN's pythonnet),
imports `AlgorithmImports`, and starts LEAN's handlers from `./config.json`. klean:

1. installs `RESEARCH_PACKAGES` (JupyterLab 4.5.1 and clr-loader 0.2.9, as in LEAN's Docker
   images; ipykernel; matplotlib 3.8.4) into the workspace's Python 3.11 env, once;
2. writes `<workspace>/.klean/research/config.json` (data folder, `composer-dll-directory` =
   the launcher folder, `object-store-root` = `<workspace>/storage`, LEAN's log to
   `.klean/research/log.txt`, plus the workspace's LEAN keys), a copy of `krx_models.py` in
   `.klean/research/lib/` (appended to `sys.path`, so a project's own copy wins), and an IPython
   startup file in `.klean/research/ipython/profile_default/startup/` that puts the launcher
   folder on `sys.path`, runs LEAN's own `start.py` from the config folder, then calls
   `Config.SetConfigurationFile(<absolute path>)`;
3. runs `python -m jupyter lab` from the 3.11 env in the project folder with `IPYTHONDIR`
   pointing at that profile, `DOTNET_ROOT` (clr-loader needs it), `PYTHONNET_PYDLL`, a random
   token, 127.0.0.1 only, no news feed or update check (`--LabApp.news_url=None`,
   `NeverCheckForUpdate`), and `--allow-root` only when running as root.

Why `SetConfigurationFile`: `QuantBook()` calls `Config.Reset()`, which re-reads `config.json`
from the *current* folder, the project's. LEAN's Docker image keeps a config there; klean
points LEAN at its own file instead, so a project's own `config.json` (the LEAN CLI keeps
project settings in one) is never read as an engine config.

`--execute` runs `jupyter nbconvert --execute` with the same environment, for scripts and tests.
Harmless log lines in `log.txt`: `QuantBook failed to determine Notebook kernel language` (only
outside Jupyter) and `SecurityIdentifier.TryParseProperties … '<label>'` (LEAN's pandas helper
trying chart labels as symbols).

## Live paper trading

Paper only: klean has two brokerages, both paper, and no real-money one (see the guard test in
`tests/klean/test_klean_kis.py`).

- **Deploy** (`live.deploy`): refuses a project whose models copy isn't current (live runs read
  the KRX universe through it; `--models-as-is` overrides); copies the code into `code/`; writes
  `ledger.json` (cash, `start_cash`, holdings, open orders, fills, daily equity, `broker`) and
  `deployment.json` (parameters, first session, `backdated`, `broker`, for KIS-PAPER the masked
  account id `kis_account`). KIS-PAPER: no backdating, one running deployment per account, the
  starting cash is the account's total.
- **Sessions** (`pending_sessions`): paper, every trading day in the data after the ledger's
  `last_session`, oldest first; KIS-PAPER, only the previous trading day by the Korean clock
  (`kis.now_kst`, fixed by `KLEAN_KIS_NOW` in tests), once.
- **A session** (`run_session`): one LEAN live-mode process with the frozen code; the config
  sets klean's `KrxDailyDataQueue` and `KrxPaperBrokerage` (or `KisPaperBrokerage` with
  `krx-kis-prices`), `krx-ledger` and `krx-session-date`; `KRX_SESSION_DATE` in the environment
  for the universe reader. The brokerage settles the previous day's orders before LEAN reads the
  account; `KrxSession.StopWhenDone` ends the run once the day's data is processed and the
  algorithm is quiet (5 s), or after 180 s without data.
- **Success**: the console has `session <day> done (data processed)` and the ledger's
  `last_session` is the day. Otherwise the ledger is restored from `ledger.json.before`, the
  error is recorded under `runs`, and the next run retries the day (`run` stops at the first
  failure, so days stay in order).
- **KIS-PAPER timing** (`run`): only in the pre-open auction, 08:30–08:59:30 KST on a trading
  day (`kis.in_pre_open`; `--now` / `krx-kis-any-time` override); the plugin checks the same
  window before sending an order. Orders are day orders (`ORD_DVSN` 01 market, 00 limit); the
  next session reads their fills (`inquire-daily-ccld`) before the algorithm starts.
- `klean update data` calls `run_all` after installing the data; KIS-PAPER deployments skip
  themselves outside their window.

## GUI actions

POST endpoints (all need the token header): `/api/backtest`, `/api/report`, `/api/optimize`
(validated with `optimize(estimate=True)` first; progress lines kept in the job),
`/api/live-deploy`, `/api/live-run`, `/api/live-stop`, `/api/research` (one JupyterLab for the whole workspace, `research.start_workspace_server`, started in
a thread after installing the packages if needed; GET reports `off | installing | starting | ready |
failed | stopped`; JupyterLab's CSP lets only the GUI's origin frame it; terminated when the GUI stops,
also on SIGTERM and SIGHUP), `/api/run-rename` and `/api/run-delete` (`stored_run`: only a folder
directly under `<project>/backtests/`, inside the workspace, and not running; rename keeps the
timestamp prefix).

## GUI security

`ThreadingHTTPServer` on 127.0.0.1, random port by default. Every request needs the random token
(query string or `X-Klean-Token` header); POSTs need the header (a cross-site form can't set it).
Every project, run and file path is resolved and must be inside the workspace (code files inside
the run's snapshot). The page's scripts and styles (`/static/…`, code only, no data) load without the token; only `.js`
and `.css` files inside `klean/static` are served. The page itself has a Content-Security-Policy
allowing only its own scripts (no inline or third-party ones), frames only from 127.0.0.1 (the
Research tab's JupyterLab), and no framing by other sites.
Reports are served with a Content-Security-Policy allowing no scripts.
`Referrer-Policy: no-referrer` keeps the token out of requests the report page makes.
