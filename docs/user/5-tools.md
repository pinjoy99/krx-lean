# 5. Optimize, report, compare, GUI

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
klean backtest Top20CS --build-config Debug --output ~/runs/debug-1
```

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

Reports are only made for runs that completed. Notes: the page loads fonts and the logo from the internet (offline it shows plain styling);
"Capacity (USD)" shows "-"; the crisis charts are US/global events and are empty outside your
data's dates.

## GUI

```bash
klean gui                         # opens http://127.0.0.1:<port>/?token=… in the browser
klean gui --port 8765 --no-browser
```

| Page | Shows |
|---|---|
| Workspace | projects with their last run, data status, setup check, settings |
| Project | runs (tick two or more → Compare), optimizations, and a form to start a backtest |
| Run | figures, equity vs KOSPI 200, drawdown, statistics, orders, log, **code**, run record; *Make LEAN report* / *Open report* |
| Optimization | target by parameter, ranked runs, Compare |
| Compare | equity curves overlaid, statistics side by side |

It listens on 127.0.0.1 only and needs the token in the printed URL; keep that URL to yourself.
Under WSL2 the page opens in your Windows browser (with `wslu` installed), or open the printed
URL yourself. Stop it with Ctrl+C. It doesn't edit code: use your editor.

## Other commands

```bash
klean project-delete Old           # asks you to type the name
klean data status
klean lean status                  # LEAN commit in use and build state
klean doctor
```

## Updating LEAN

`klean lean update` checks out and rebuilds the tested commit; `--commit C` another one. After
changing LEAN, rerun a reference backtest and `klean compare` it with an earlier run before
trusting new results.

Next: [6. Daily update](6-daily-update.md).
