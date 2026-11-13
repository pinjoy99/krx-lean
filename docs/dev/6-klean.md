# 6. klean internals

klean is the local part of the LEAN CLI's workflow, rebuilt on a LEAN source build: standard
library only, no Docker, no account. Projects keep the LEAN CLI's layout, so a Python project
also runs under `lean backtest`.

| Module | Does |
|---|---|
| `workspace.py` | `klean.json` (load/save, found upwards from the current folder), tested LEAN commit, Python package pins, `dotnet` and libpython lookup, `doctor` checks |
| `cli.py` | commands; the `<verb> <noun>` commands (`install lean/python/data` (incl. `--demo`), `update data/lean/models/klean/all`, `status …`, `create/delete project`) plus the old names as hidden aliases; `init`, `config` |
| `projects.py` | templates (Python, C#), algorithm class detection, `.csproj` (references the launcher DLLs; excludes `backtests/**`, `optimizations/**`) |
| `backtest.py` | `prepare` (py_compile + requirements, or `dotnet build`), `run_once` (code snapshot, per-run config, launcher, manifest), `backtest` |
| `results.py` | finding runs, statistics, equity curves, `compare`, logs, source files and the code snapshot, `status data` |
| `optimize.py` | grid search |
| `report.py` | LEAN's Report |
| `research.py` | Jupyter with LEAN's QuantBook |
| `gui.py`, `static/index.html` | local web page |

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

Each project has its own copy of the models (copied by `create project`), so a project stays
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

## GUI actions

POST endpoints (all need the token header): `/api/backtest`, `/api/report`, `/api/optimize`
(validated with `optimize(estimate=True)` first; progress lines kept in the job),
`/api/research` (one JupyterLab per project through `research.start`; terminated when the GUI
stops, also on SIGTERM), `/api/run-rename` and `/api/run-delete` (`stored_run`: only a folder
directly under `<project>/backtests/`, inside the workspace, and not running; rename keeps the
timestamp prefix).

## GUI security

`ThreadingHTTPServer` on 127.0.0.1, random port by default. Every request needs the random token
(query string or `X-Klean-Token` header); POSTs need the header (a cross-site form can't set it).
Every project, run and file path is resolved and must be inside the workspace (code files inside
the run's snapshot). Reports are served with a Content-Security-Policy allowing no scripts.
`Referrer-Policy: no-referrer` keeps the token out of requests the report page makes.
