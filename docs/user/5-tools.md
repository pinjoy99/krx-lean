# 5. Tools: compare, optimize, report, research, GUI

## Naming runs

Commands that read results take a **project** (its latest run), `PROJECT/RUN` (a run folder name
or a unique prefix), or a results folder path:

```bash
klean logs Top20                            # latest run
klean logs Top20/2026-11-02_10-15           # by name prefix
klean logs ~/krx-workspace/Top20/backtests/2026-11-02_10-15-00 --console   # LEAN's output
```

## Backtest options

```bash
klean backtest Top20 --parameter holdings 25 --backtest-name h25   # parameters, named run
klean backtest Top20 --extra-config maximum-data-points-per-chart-series 4000   # any LEAN config key
klean backtest Top20 --timeout 600                                 # stop it if it runs over 10 minutes
klean backtest Top20 --parameter slippage_ticks 1                  # switch slippage on (off by default)
klean backtest Top20 --detach                                      # run in the background, return at once
klean backtest Top20CS --build-config Debug --output ~/runs/debug-1
```

A run on a terminal shows the elapsed time while LEAN works; Ctrl+C stops it. With `--detach`
klean prints the run folder and returns; `klean logs Top20` says `STILL RUNNING` until it's done
(klean's own output is in `klean-detached.log` in the run folder), and the GUI shows the run as
"running".

LEAN config keys you want for every run go in the workspace: `klean config set KEY VALUE`
(`klean config list` shows them).

## Compare

```bash
klean compare Top20 Top20CS                 # latest runs of two projects
klean compare Top20/2026-11-02_10-15 Top20/2026-11-02_11 --all
```

Statistics side by side (differences marked `≠`), equity curves compared point by point, and a
verdict: `IDENTICAL` or `DIFFERENT: …`. Use it before and after a change, or to check that a
Python and a C# version of a strategy agree.

## Optimize (parameter search)

```bash
klean optimize Top20CS --parameter holdings 5 30 5 --constraint "Drawdown < 35"
klean optimize Top20CS --parameter holdings 10 30 10 --parameter lookback 20 60 20 \
    --target "Compounding Annual Return" --max-concurrent-backtests 4 --name grid-1
klean optimize Top20CS --parameter holdings 5 30 5 --estimate      # only count the backtests
```

- `--parameter NAME MIN MAX STEP` (repeatable): every value from MIN to MAX inclusive; with
  several parameters every combination runs (grid search).
- `--target` (default `Sharpe Ratio`) is any statistic name; `--target-direction max|min`.
- `--constraint "STATISTIC OP VALUE"` (repeatable; `< <= > >= == !=`), in the units the
  statistics show: `Drawdown < 25` means 25%. Runs that fail are listed but can't be best.
- `--max-concurrent-backtests` (default half the CPU cores); `--max-backtests` (default 500).
- `--timeout SECONDS`: stop any single backtest that runs longer; it's listed as a failed run.

The project is compiled once; every combination is a normal run under
`Top20CS/optimizations/<date>_<time>[_name]/<NNN>_holdings=25/`, with `optimization.json`
(every run's parameters, target value and constraint result, and the best run) and one shared
`code/` copy. The ranked table is printed at the end (★ = best). Prefer C# projects for
optimizations: Python runs are several times slower.

Beware of overfitting: the best of many runs on the same history is optimistic. Keep a later
period aside and check the chosen parameters on it.

## Report

```bash
klean report Top20                      # latest run → <run>/report.html
klean report                            # the workspace's latest run
klean report Top20/2026-11-02_10-15 --strategy-version v1 --pdf
```

LEAN's own strategy report: key statistics, monthly and annual returns, cumulative returns vs
KOSPI 200, drawdown periods, asset allocation, rolling beta and Sharpe, leverage, exposure,
crisis periods, parameters. About 40 s per report. The first time, klean builds LEAN's report
program (~30 s) and installs matplotlib into the Python 3.11 environment.

Options: `--report-destination FILE.html`, `--overwrite`, `--strategy-name`,
`--strategy-version`, `--strategy-description`, `--css FILE` (style overrides), `--html FILE`
(your own template). `--pdf` needs `wkhtmltopdf` or Chromium/Chrome on the PATH
(`sudo apt install -y wkhtmltopdf`).

Reports are only made for runs that completed. The page loads fonts and the logo from the
internet (offline it shows plain styling); "Capacity (USD)" shows "-"; the crisis charts are
US/global events and are empty outside your data's dates.

## Research notebooks

```bash
klean research Top20                  # JupyterLab in the browser, with the project's research.ipynb
klean research Top20 --port 8888 --no-browser
klean research Top20 --execute        # run research.ipynb without a browser → research.executed.ipynb
```

A Jupyter notebook for exploring data before (or after) writing a strategy, like the LEAN CLI's
`lean research` but without Docker. LEAN is already loaded in every notebook: `QuantBook()` gives
history and indicators from the workspace's KRX data, and the project's `krx_models.py` is
importable (`KrxBoards`, `load_index` for KOSPI / KOSPI 200).

```python
qb = QuantBook()
symbol = qb.add_equity("005930", Resolution.DAILY, Market.KRX).symbol
history = qb.history(symbol, datetime(2020, 1, 1), datetime(2025, 12, 31), Resolution.DAILY)
sma = qb.indicator(SimpleMovingAverage(60), symbol, datetime(2020, 1, 1), datetime(2025, 12, 31), Resolution.DAILY)
```

- **First use:** klean installs JupyterLab 4.5.1, ipykernel, clr-loader 0.2.9 and matplotlib
  into the Python 3.11 environment (the versions of LEAN's Docker image); a few minutes and a few
  hundred MB.
- Open notebooks with `klean research`, not plain `jupyter lab`: klean is what loads LEAN into
  the notebook.
- If the project has no `research.ipynb`, klean writes a starter one (history of one stock, a
  60-day average, the stock against the KOSPI 200). Your notebooks are never overwritten.
- Jupyter listens on 127.0.0.1 with a random token in the printed URL, and doesn't check the
  internet for news or updates; stop it with Ctrl+C. Under WSL2 it opens your Windows browser
  (with `wslu`), or open the URL yourself.
- Notebooks are Python, also in C# projects (LEAN's C# notebooks need .NET Interactive; not
  supported).
- `from AlgorithmImports import *` (done for you) replaces Python's `time` module with
  `datetime.time`: use `import time as time_module` if you need it.
- LEAN's own log goes to `<workspace>/.klean/research/log.txt`, the object store
  (`qb.object_store`) to `<workspace>/storage/`.

## GUI

```bash
klean gui                         # opens http://127.0.0.1:<port>/?token=… in the browser
klean gui --port 8765 --no-browser
```

| Page | Shows |
|---|---|
| Workspace | projects with their last run, data status, setup check, settings |
| Project | runs (tick two or more → Compare), optimizations; forms to start a backtest and an optimization (grid search); a button that starts JupyterLab for the project |
| Run | figures, equity vs KOSPI 200, drawdown, statistics, orders, log, **code**, run record; *Make LEAN report* / *Open report*; *Rename* and *Delete* |
| Optimization | target by parameter, ranked runs, Compare |
| Compare | equity curves overlaid, statistics side by side |

It listens on 127.0.0.1 only and needs the token in the printed URL; keep that URL to yourself.
Under WSL2 the page opens in your Windows browser (with `wslu` installed), or open the printed
URL yourself. Stop it with Ctrl+C (notebooks started from the page stop with it). *Delete*
removes a run's folder for good, after asking; only runs in a project's `backtests/` folder can
be renamed or deleted, and never one that is still running. It doesn't edit code: use your
editor.

## Other commands

klean's commands read `klean <verb> <noun>`: `install`, `update`, `status`, `create` and
`delete` take a noun (`lean`, `python`, `data`, `models`, `project`, …); `klean <verb> --help`
lists them. (The 0.0.9 names such as `klean install-lean` or `klean project-create` still work.)

```bash
klean delete project Old     # asks you to type the name
klean status data            # data range, securities, indices
klean status models          # are the projects' KRX models current?
klean status lean            # LEAN commit in use and build state
klean status all             # all three
klean update data            # new KRX days into the workspace (6. Daily update)
klean update all             # krx-lean, LEAN if needed, data (6. Daily update)
klean doctor
```

## Updating LEAN

`klean update lean` checks out and rebuilds the tested commit; `--commit C` another one. After
changing LEAN, rerun a reference backtest and `klean compare` it with an earlier run before
trusting new results.

Next: [6. Daily update](6-daily-update.md).
