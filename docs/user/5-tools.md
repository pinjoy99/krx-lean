# 5. Tools: compare, optimize, report, research, GUI, live paper trading

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

The easiest way in is the GUI's **Research** dashboard (`klean gui`, pick the project in the top
bar, then *Research*): JupyterLab inside the page. Each project opens in **its own layout**: the
files and tabs you left open for it. The first time, that's the strategy (`main.py` / `Main.cs`)
and `research.ipynb` side by side. The first time, klean also installs JupyterLab (a few
minutes). On its own:

```bash
klean research Top20                  # JupyterLab in the browser, on the project's layout
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
- **Layouts:** a project's layout is kept in the project, `.jupyter/layout.json` (hidden; file
  paths relative to the project, so it survives a rename and travels with a copied folder; left
  out of git by its own `.gitignore`, of run snapshots and of live deployments). klean saves it
  when you switch to another project or dashboard, every minute, and when JupyterLab stops. In
  the Research bar: *Reset layout* (back to the strategy and `research.ipynb`) and *Shut down
  kernels* (the project's notebook kernels, with how many are running).
- **Kernels** belong to JupyterLab, not to a layout: switching project leaves the other
  project's kernels running. Each holds LEAN in memory, so JupyterLab stops a kernel after an hour
  idle with no notebook open on it (closing a notebook's tab doesn't stop its kernel); kernels of
  open notebooks keep running until you shut them down.
- `klean create-project` writes a starter `research.ipynb` (history of one stock, a 60-day
  average, the stock against the KOSPI 200); for an older project without one, `klean research`
  writes it. Your notebooks are never overwritten.
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

Four dashboards; the Workspace is the landing page, and each project has the other three. The
top bar is the same everywhere: *Workspace*, the **project** (choosing another one keeps the
dashboard: from Top20's Backtest to Momentum's Backtest), and the project's **Research ·
Backtest · Live**. On the Workspace page it shows the last project you used.

| Dashboard | Shows |
|---|---|
| **Workspace** | left: projects with their number of backtests, last backtest, number of live runs and last live run (a project's name opens its Research, the run columns open Backtest or Live), and *New project* (name, language, template → *Create project*, as `klean create-project`; then the new project's Research dashboard opens with `main.py` (or `Main.cs`) and `research.ipynb` side by side); right: KRX data, setup check, settings |
| **Research** | JupyterLab inside the page (LEAN loaded in every notebook; files, editor, terminal), on the project's own layout; *Reset layout*, *Shut down kernels*, *Open in a new tab*. *Open JupyterLab (all files)* on the Workspace page shows the whole workspace instead |
| **Backtest** | left: *New backtest* and *New optimization* forms (prefilled with the parameters the strategy reads, see below), the runs (tick two or more → *Compare selected*), the optimizations; right: the selected run (the latest by default: figures, equity vs KOSPI 200, drawdown, statistics, orders, log, code, run record, *Make LEAN report*, *Rename*, *Delete*), an optimization, or the comparison |
| **Live** | left: *New paper deployment* (parameters from one of the project's backtests, starting cash, optional first day) and the deployments; right: the selected one's account, equity vs KOSPI 200, positions, waiting orders, fills, daily runs (with LEAN's console output); *Trade new days*, *Stop* |

**Parameters in the forms.** klean reads the strategy's code for `get_parameter("name", default)`
/ `GetParameter("name", default)` and `set_period` / `SetPeriod` (`start_date`, `end_date`), and
lists them with their defaults (hover a row: where it's read). *New backtest* sends only the
values you change, so a run's record lists just those. *New optimization* gets a row per numeric
parameter at its default (min = max: kept fixed) with a step (1 for whole numbers); widen the
ranges you want searched and remove the others. A default klean can't work out (a computed
value) is left blank; digits with a leading zero, such as a stock code, count as text.

Charts: drag across a chart to zoom into a period, double-click to zoom out; the legend under
the chart shows the values at the cursor (the latest ones otherwise); *log scale* on equity
charts makes long periods easier to read.

It listens on 127.0.0.1 only and needs the token in the printed URL; keep that URL to yourself.
Under WSL2 the page opens in your Windows browser (with `wslu` installed), or open the printed
URL yourself. Stop it with Ctrl+C or by closing its terminal (JupyterLab stops with it).
*Delete*
removes a run's folder for good, after asking; only runs in a project's `backtests/` folder can
be renamed or deleted, and never one that is still running. To edit a strategy, open its
`main.py` in the Research tab (JupyterLab's editor; files save automatically) or use your own
editor.

## Live paper trading (Live)

Your strategy, unchanged, runs in LEAN's own live mode on the daily KRX data, with klean's
paper broker: no real broker, no real money. LEAN ignores the strategy's start and end dates
in live mode (as `lean live` does).

```bash
klean live deploy Top20 --from-run Top20/2026-11-20_10-12-03_holdings30   # that backtest's parameters
klean live deploy Top20 --parameter holdings 30 --cash 50000000 --name h30
klean live status                    # deployments: days, equity, profit, waiting orders
klean live run                       # trade the new trading days (`klean update data` does this)
klean live stop Top20 <id>           # stops it; its account and history stay
```

How a day works: after `klean update data` brings in day T, klean starts LEAN in live mode
for T. The paper broker first fills the orders placed on the previous trading day at T's open
(KRX commission, sell tax by settlement date, `slippage_ticks`), then the strategy sees T's
prices (and its universe, for universe strategies), places orders, and the run ends. Those
orders fill at the next trading day's open, on the next run. Missed days are caught up one
by one, in order. A day that fails (an error, or the strategy got no data within 3 minutes) leaves
the account as it was and is retried on the next run.

- A deployment freezes the project's code and parameters; editing the project later doesn't
  change it. It needs the project's KRX models to be current (`klean update models
  NAME` first; `--models-as-is` for a copy you edited on purpose). It starts on the trading day after the latest data, so it trades after the next
  `klean update data` ("waiting for data" until then).
- `--start YYYY-MM-DD` on or before the latest data makes a **backdated** deployment, to try it
  on days the data already has; it's labeled so everywhere.
- Cash comes from the deployment (`--cash`, default ₩100,000,000), not from `set_cash`.
- The strategy's clock (`self.time`) is when the run happens, not the day of the data (KRX
  publishes a day's prices the next day). Code that acts in `on_data` is unaffected;
  scheduled events and "first trading day of the month" rules follow the run's date.
- Compared with a backtest: orders fill at the same next-day open, at the same price. Universe
  strategies trade one day earlier than in a backtest (LEAN's backtests apply a daily universe
  a day after its date; live mode uses it the same day). The commission is on the traded
  value (the backtest's KRX fee model uses the previous close: a few hundred won apart).
- Supported orders: market (filled at the next open), market-on-open, market-on-close (next
  day's close), limit (at the open if better, else at the limit if the day's range reaches
  it; otherwise it keeps waiting). No short selling; a buy larger than the cash is reduced.
  Not yet: splits and dividends on holdings, the ±30% daily price limits.
- Files: `<project>/live/<id>/` with `deployment.json`, `code/` (the frozen code),
  `ledger.json` (cash, holdings, waiting orders, fills, daily equity) and `runs/<day>/` (LEAN's
  output for each day).
- How it works: klean's LEAN plugin (`klean/plugin`, built into your LEAN build the first time)
  is a daily data feed and a paper brokerage; KIS-PAPER (below) is a second brokerage in it, for
  a Korea Investment 모의투자 account.

### KIS-PAPER: a Korea Investment 모의투자 (paper) account

The same deployment can send its orders to a **KIS 모의투자 (paper trading) account** instead of
klean's own paper broker: broker `kis-paper`. klean only ever connects to KIS's 모의투자 server
(`openapivts.koreainvestment.com`); it has no real-money mode. The keys' names say so: `KIS_PAPER_…`.

1. Get Open API keys for your KIS 모의투자 account at apiportal.koreainvestment.com (모의투자 has
   its own app key and account number). Put them in `~/.config/krx-lean.env`, next to the KRX
   key, and keep that file private (`chmod 600 ~/.config/krx-lean.env`):

   ```
   KIS_PAPER_APP_KEY=...
   KIS_PAPER_APP_SECRET=...
   KIS_PAPER_ACCOUNT=12345678-01
   ```

2. Check them: `klean live kis-check` (logs in, shows the 모의투자 account and one day's prices).
3. Deploy: `klean live deploy Top20 --broker kis-paper`. The account's cash and every holding
   are the strategy's, so one account serves one strategy: klean refuses a second running
   deployment on the same account.
4. Schedule `klean live run` inside KRX's **pre-open auction, 08:30–08:59 KST**, on trading
   days. At that time the strategy gets the previous trading day's prices from KIS (the KRX
   files have them only later that day; universe strategies use the latest KRX universe file),
   and its market orders join the opening auction: they fill at the open, as in a backtest.
   Runs outside the window are skipped, so two schedules are fine:

   | You are in | Run `klean live run` at (local) |
   |---|---|
   | Korea | 08:35 |
   | US Eastern | 18:35 in winter (EST), 19:35 in summer (EDT): schedule both |

   A script for it, `~/bin/klean-kis-paper` (`chmod +x`; same environment lines as `~/bin/krx-update`
   in [6. Daily update](6-daily-update.md#run-it-automatically)):

   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   exec >> "$HOME/klean-kis-paper.log" 2>&1
   export DOTNET_ROOT="$HOME/.dotnet"
   export PATH="$HOME/.krx-lean/venv/bin:$HOME/.dotnet:$HOME/.local/bin:$PATH"
   echo "=== $(date)"
   cd "$HOME/krx-workspace" && klean live run
   ```

   Linux cron, with the system clock on US Eastern: `35 18,19 * * 0-4 $HOME/bin/klean-kis-paper`
   (Sunday to Thursday evening is Monday to Friday morning in Korea; on Korean time:
   `35 8 * * 1-5 …`). WSL2, Windows Task Scheduler (PowerShell):

   ```powershell
   schtasks /Create /TN "klean-kis-paper-est" /SC DAILY /ST 18:35 /TR "wsl.exe -d Ubuntu -e /home/<you>/bin/klean-kis-paper"
   schtasks /Create /TN "klean-kis-paper-edt" /SC DAILY /ST 19:35 /TR "wsl.exe -d Ubuntu -e /home/<you>/bin/klean-kis-paper"
   ```

- The next run reads the fills from KIS (prices KIS reports; its fees and taxes are in the
  account's cash). Orders are day orders: what didn't fill is listed under *Notices*.
- `klean live run --now` runs outside the window (market orders then fill at once, at the
  current price): for trying the 모의투자 account during market hours.
- Supported orders: market, market-on-open, limit. A KIS-PAPER deployment can't be backdated.
- Tokens are cached in `~/.klean/kis-token-paper-*.json` (KIS issues one a day, at most one a
  minute). klean never writes the keys anywhere else and never shows them.
- klean and krx-lean are for research and paper trading. They place no real-money orders and
  are not investment advice.

## Other commands

`install`, `update` and `status` take a noun (`klean install lean`, `klean update data`,
`klean status all`); `klean <verb> --help` lists them. Projects are `klean create-project` and
`klean delete-project`. (Older names such as `klean install-lean` or lean's `project-create` still
work.)

```bash
klean delete-project Old     # asks you to type the name
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
