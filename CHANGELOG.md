# Changelog

## 0.0.34 — 2026-11-26

- Starting cash is ₩100,000,000 everywhere by default: the top-market-cap template and example
  (Python and C#) started with ₩1,000,000,000; the other templates and live deployments already
  used ₩100,000,000. Existing projects keep the cash in their own `main.py` / `Main.cs`.

## 0.0.33 — 2026-11-26

Backtest dashboard:
- The left column reads top to bottom: *New backtest*, *Backtest runs*, *New optimization*,
  *Optimization runs* (always shown).
- Deleting or renaming a run refreshes the runs list and the right column at once (deleting the
  run shown by default left the page unchanged).
- The Equity chart names the run's own benchmark instead of always "KOSPI 200": klean finds it from
  the benchmark's values (an index, or a stock named in the code or parameters), so a strategy
  that picks KOSDAQ at run time shows KOSDAQ; "Benchmark" if it can't tell.
- The Drawdown chart says the maximum drawdown, its date, the peak before it and when (or whether)
  it recovered.

## 0.0.32 — 2026-11-26

- The GUI uses the krx-lean site's icon (pinjoy99.github.io/krx-lean): in the browser tab and
  next to "klean" in the top bar.

## 0.0.31 — 2026-11-26

- `krx_benchmark("005930")` / `KrxIndex.Benchmark("005930")` with no data for that stock said only
  "no 005930 index data"; for a code it now names both places it looked (the index file and the
  stock's daily file) and how to get the data. Codes with letters (`0041B0`) count as codes.
  (A project whose models copy predates 0.0.30 shows the old index-only error:
  `klean update models NAME`.)

## 0.0.30 — 2026-11-26

- **A stock or ETF as the benchmark:** `krx_benchmark("005930")` / `KrxIndex.Benchmark("005930")`,
  its daily closes adjusted for splits and dividends exactly as LEAN adjusts prices (checked
  against LEAN over a split and dividends; Python and C# identical). Indices as before.
  `set_benchmark("005930")` gives no benchmark (LEAN makes a bare ticker a US stock and asks for
  hourly data): the docs say so. The KRX models changed: `klean update models NAME` (or `--all`)
  for existing projects (a live deployment needs the current models).

## 0.0.29 — 2026-11-25

- **One browser tab at a time per project's Research.** With a project's Research open in two
  tabs, JupyterLab gave the second an empty layout, both tabs edited their own copies of the same
  files, and saving from both ended in "File Changed: overwrite or revert?" (one side's edits
  lost). Now opening it in another tab, or with *Open in a new tab*, moves it there: the first
  tab saves, unloads JupyterLab and shows "open in another klean tab" with *Use it here*.

## 0.0.28 — 2026-11-25

- **Edits in Research are saved when you click away.** JupyterLab saved files only every 2
  minutes, so a backtest started right after editing `main.py` could run the old code, and
  clicking a top-bar tab (*Backtest*, *Live*, another project) replaced JupyterLab's frame and
  dropped the unsaved edit. klean now installs the JupyterLab extension
  `jupyterlab-autosave-on-focus-change` 0.4.1 (BSD-3) with JupyterLab: a file is saved as soon as
  it loses focus, also to klean's page. Existing environments get it the next time Research
  starts. It can be turned off in JupyterLab's settings.
- Pages open faster: the top bar's project list comes from a small `/api/projects` (it used to
  load the whole Workspace summary, setup check included, before every page) and loads beside the
  page, not before it.

## 0.0.27 — 2026-11-25

- Fix (0.0.26): two klean processes starting at the same moment could each conclude that file
  locks don't work in a folder (they checked with one shared probe file) and then run without
  the lock. Each process now checks with its own file, and only an "unsupported" error counts.
  Found by CI on Ubuntu; a test now races eight processes through the check.
- "waiting for …" / "skipped, already being run by …" messages name the other process (its pid)
  even when it has only just taken the lock.

## 0.0.26 — 2026-11-25

klean processes (the GUI, schedules, the command line) no longer collide when they run at the
same time:

- **Live runs:** one run at a time per deployment. A second `klean live run`, `klean update data`
  or GUI run skips it ("already being run by pid …"), and the days to process are worked out
  inside the lock: no trading day processed twice, **no KIS-PAPER order sent twice**. *Stop*
  during a run stops it after the day in progress.
- **One KIS 모의투자 account, one strategy, in all your klean workspaces:** deploying checks and
  claims the account in one step (`~/.klean/kis-accounts.json`); *Stop* releases it. Existing
  KIS-PAPER deployments are claimed on their next run.
- **Data updates** replace each file in one step (a run reading it sees the old file or the new
  one, never part of one) and wait for a live trading day in progress; two updates never overlap.
- **pip** installs into the shared Python environment one at a time, and `requirements.txt` is
  skipped when nothing changed (backtests start faster).
- **The live plugin** is built once when two runs need it, and replaced in one step.
- Locks are released by the system when a process ends, even after a crash; klean warns if the
  workspace is on a drive without file locks.

## 0.0.25 — 2026-11-24

- **Parameters found in the strategy's code.** The Backtest dashboard's *New backtest* form lists
  the parameters the strategy reads (`get_parameter("name", default)` / `GetParameter`, and
  `set_period` / `SetPeriod` as `start_date` / `end_date`) with their defaults; only the values
  you change are sent. *New optimization* starts with one row per numeric parameter at its
  default (min = max) and a step to widen it. Python is read with its syntax tree (defaults such
  as `str(self.HOLDINGS)` resolve), C# with patterns; the KRX models file is left out.

## 0.0.24 — 2026-11-24

- **One JupyterLab layout per project.** Each project opens in its own layout (open files, tabs,
  splits), kept in the project as `.jupyter/layout.json` with paths relative to the project: it
  survives a rename, travels with a copied folder, and is left out of git (its own `.gitignore`),
  run snapshots and live deployments. Saved when you switch project or dashboard, every minute,
  and when JupyterLab stops; `klean research P` uses it too. Before, projects shared one layout
  after their first opening.
- Research bar: *Reset layout* (the strategy and `research.ipynb` side by side again) and *Shut
  down kernels* (this project's notebook kernels, with how many are running).
- JupyterLab stops a kernel after an hour idle with no notebook open on it (each holds LEAN in
  memory; closing a tab doesn't stop its kernel). Layouts are stored per klean workspace.
- **Top bar:** *Workspace*, a **project switcher** and the project's **Research · Backtest ·
  Live** on every dashboard. Choosing another project keeps the dashboard; the Workspace page
  shows the last project used. The per-page Research/Backtest/Live buttons and the Research
  page's notebook list are gone; *Open JupyterLab (all files)* on the Workspace page opens the
  whole workspace. The top bar wraps on narrow windows.

## 0.0.23 — 2026-11-24

- **New project in the GUI:** the Workspace dashboard has a *New project* box (name, language,
  template → *Create project*). It runs `klean create-project`, then opens the new project's
  Research dashboard with the strategy (`main.py`, or `Main.cs` in C#) and `research.ipynb`
  side by side in JupyterLab.
- `klean create-project` also writes the starter research notebook, `research.ipynb` (before,
  `klean research` wrote it the first time). Older projects still get one from `klean research`.
- Project names must stay inside the workspace (no `..`, absolute paths, hidden folders, or
  `data` / `storage`).
- The Research dashboard opens a project's notebook by its path in the workspace.

## 0.0.22 — 2026-11-23

Documentation for the current scope: research and paper trading, no real-money orders.

- README (English and Korean), the beginner's guide (both languages), the users and developers
  tracks, CONTRIBUTING and SECURITY describe daily paper trading (klean's paper broker or a KIS
  모의투자 account) as in scope and real-money trading as out of scope; the guide's FAQ no
  longer says nothing connects to a broker.
- Users: KIS-PAPER keys next to the other keys, a `~/bin/klean-kis-paper` script and cron line
  for the pre-open schedule, and why `klean update data` skips KIS-PAPER deployments; a
  troubleshooting table for live paper trading.
- Developers: how a live session runs, succeeds or rolls back (6. klean internals); the plugin
  in the architecture; the roadmap's live items; a KIS-PAPER step in the release checklist.

## 0.0.21 — 2026-11-23

- **KIS-PAPER broker** for live deployments: `klean live deploy NAME --broker kis-paper` sends
  the strategy's orders to a **Korea Investment 모의투자 (paper trading) account**; klean
  connects only to KIS's 모의투자 server and has no real-money mode. Keys in
  `~/.config/krx-lean.env`: `KIS_PAPER_APP_KEY`, `KIS_PAPER_APP_SECRET`, `KIS_PAPER_ACCOUNT`;
  `klean live kis-check` tests them. Runs happen in KRX's pre-open auction (08:30–08:59 KST): the
  strategy sees the previous trading day's prices from KIS (universe strategies: the latest KRX
  universe file), its market orders fill at the open, and the next run reads the fills back.
  Tokens are cached in `~/.klean/`. `klean live run --now` for trying it in market hours.
- One 모의투자 account, one strategy: a second running deployment on the same account is refused
  (a strategy treats the whole account as its own).
- Live dashboard: a broker choice when deploying, and a broker badge on every deployment.
- `tests/fake_kis.py`: a simulated KIS 모의투자 server; the end-to-end check runs the
  top-market-cap universe through it. A test fails if klean's code ever contains a KIS
  real-trading server address or real-account order id.
- `klean … | head` or `| grep -q` no longer ends with a broken-pipe error.
- Docs: klean and krx-lean place no real-money orders and are not investment advice.
- Not yet checked against KIS itself: the API facts come from KIS's official sample code
  (github.com/koreainvestment/open-trading-api); `klean live kis-check` is the first real test.

## 0.0.19 — 2026-11-23

- Live dashboard: "starting cash" showed the current cash; negative amounts read "−₩69,000"
  (was "₩-69,000") everywhere in the GUI.

## 0.0.18 — 2026-11-23

- `klean live deploy` refuses a project whose KRX models copy isn't current (live runs need
  the universe reader of 0.0.17): `klean update models NAME` first, or `--models-as-is`.
- A live day counts as done only when the strategy got that day's data; otherwise (an error, or
  no data within 3 minutes, down from 10) the account is restored and the day is retried on the
  next run. Before, a project with old models waited 10 minutes per day and recorded the days as
  done without trading.
- Docs: running the daily update from Windows Task Scheduler; times for KST, US Eastern, UTC.

## 0.0.17 — 2026-11-23

- **Live paper trading in LEAN's live mode** replaces 0.0.15's forward tests:
  `klean live deploy | run | status | stop`, and `klean update data` lets every running
  deployment trade the new days. The strategy runs unchanged (live mode ignores its dates);
  orders fill at the next trading day's open through klean's paper broker. Universe
  strategies work (the KRX universe reader takes the run's day from `KRX_SESSION_DATE`).
- **Live dashboard**: new paper deployment (parameters from a backtest, starting cash), the
  deployments, and for the selected one its account, equity vs KOSPI 200, positions, waiting
  orders, fills and daily runs with LEAN's console output; *Trade new days*, *Stop*.
- `set_period` stays, optional: it lets `start_date` / `end_date` parameters move a backtest.
- C# projects: `live/` is kept out of the build and klean's plugin isn't referenced (older
  project files are updated automatically).
- Checked: buy-and-hold fills match a backtest of the same days; the top-market-cap universe
  trades identically in C# and Python in live mode.

## 0.0.16 — 2026-11-23

Groundwork for live paper trading in LEAN's own live mode (commands and GUI follow).

- **klean's LEAN plugin** (`klean/plugin`, built into the LEAN build as `QuantConnect.Krx.dll`
  when first needed): `KrxDailyDataQueue` feeds one trading day of KRX bars per run;
  `KrxPaperBrokerage` keeps a paper account in `ledger.json` and fills the orders of one day
  at the next trading day's open, with KRX commission, sell tax (by settlement date) and
  slippage in ticks, before the strategy runs; each run ends by itself.
- `klean/live.py`: deployments (frozen code + paper account) and the daily runs, one LEAN
  process per trading day, catching up missed days in order.
- Checked: buy-and-hold on the demo data over three trading days fills the same shares at the
  same price as a backtest of those days. The live commission is on the traded value; the
  backtest's KRX fee model uses the previous close (₩260 apart on a ₩90M buy).

## 0.0.15 — 2026-11-23

- **Forward tests (Live dashboard, `klean live`)**: paper trading on daily data. A forward test
  freezes the project's code and parameters; after each `klean update data` it runs that code
  from its start date to the latest data with the same fees, taxes and slippage as a backtest,
  so its results are out of sample. Start one from the Live dashboard (parameters from a
  backtest) or `klean live start`; `status`, `refresh`, `stop`. A start date on days the data
  already had is labeled *backdated*. No broker, no money.
- **`set_period(self, "2011-01-01", "2026-09-30")`** (C#: `KrxModels.SetPeriod`) in the KRX
  models: the backtest period, which the `start_date` / `end_date` parameters can move. The
  templates and examples use it; forward tests need it. Existing projects: `klean update models
  NAME`, then replace `set_start_date` / `set_end_date` with `set_period`.
- Workspace dashboard: live runs per project and the last one. Live dashboard: start form,
  forward tests, the selected one's refresh history and results.

## 0.0.14 — 2026-11-23

`klean gui` is organized as four dashboards (Workspace, Research, Backtest, Live).

- **Workspace** (landing page): projects with their backtests and live runs on the left; KRX
  data, setup check and settings on the right. A project's name opens its Research.
- **Backtest**: forms, runs and optimizations on the left; the selected run (the latest by
  default), an optimization or a comparison of the ticked runs on the right. Choosing another
  run redraws only the right column, so a running backtest and the forms stay as they are; a
  finished backtest is selected automatically.
- **Research** and **Backtest** have a title bar with the project and links between the
  dashboards. **Live** is a placeholder until forward tests arrive.
- Addresses from earlier versions (`#/project/…`, `#/run/…`, `#/optimization/…`, `#/compare?…`)
  lead to the new dashboards.

## 0.0.13 — 2026-11-22

- **Research tab in `klean gui`:** JupyterLab for the whole workspace inside the page, with LEAN
  loaded in every notebook. Pick a project's `research.ipynb` at the top (or *Open … in
  Research* on a project page); notebooks run in their project's folder, so its `krx_models`
  imports. Files, code editor and terminal are JupyterLab's own. Started on first use
  (installing JupyterLab once), stopped with the GUI, also when its terminal is closed.
- The browser check runs a notebook cell in the Research tab on the LEAN kernel.
- Fix: `klean gui` could hang at start on macOS: Python's web server looks up a host name for
  127.0.0.1 (reverse DNS), which stalled there. klean's server skips that lookup.

## 0.0.12 — 2026-11-22

First step of the GUI and research upgrade (the page looks the same; the work is underneath).

- **Charts on uPlot:** zoom by dragging (double-click resets), values at the cursor in the
  legend (the latest ones otherwise), log scale for equity curves; the optimization chart marks
  the tested parameter values. uPlot 1.6.32 (MIT) is copied into `klean/static/vendor/` (no CDN).
- The page is split into modules (`klean/static/js/`: router, one module per page, charts,
  helpers) and has a Content-Security-Policy that allows only its own scripts.
- **Browser check** (`tests/gui-browser.py`, Playwright) in CI after the end-to-end check: every
  page in light and dark mode without console errors, chart zoom and legend, compare, a backtest
  started from the page.
- Checked for the next steps: JupyterLab started at the workspace folder can be embedded in the
  GUI page (LEAN kernel, the project's `krx_models` importable).

## 0.0.11 — 2026-11-13

- `klean install python` creates the environment with `uv venv --seed` instead of
  `python -m venv`, whose ensurepip step failed on some machines without saying why. An
  environment left half-made by an earlier attempt is replaced; any other existing folder is
  left alone. `klean --help` has the same layout on Python 3.10 as on 3.11+.
- Projects: **`klean create-project`** and **`klean delete-project`** (one command each, as in
  lean's `create-project` alias). 0.0.10's `create project` / `delete project` and the older
  `project-create` / `project-delete` still work, unlisted.

## 0.0.10 — 2026-11-13

- **Commands read `klean <verb> <noun>`:** `install lean | python | data`, `update data | lean |
  models | klean | all`, `status data | lean | models | all`, `create project`, `delete project`.
  `klean --help` groups them (setup, keeping up to date, projects and runs) and lists
  `--timeout` / `--detach`.
- New: **`klean update klean`** (git pull of the krx-lean clone; reinstalls if `pyproject.toml`
  changed), **`klean update all`** (klean, then LEAN only if krx-lean now uses another commit,
  then data, then a models check; the steps after the pull run with the new code) and
  **`klean status all`**.
- The 0.0.9 names (`install-lean`, `install-python`, `data install|status`, `project-create`,
  `project-delete`, `lean status|update`, `models status|update`, bare `update`) still work but
  are no longer listed in `--help`. All docs use the new names.

## 0.0.9 — 2026-11-11

- **KOSDAQ** is in scope. `krx-lean all` / `klean update` also download KOSDAQ prices and the
  KOSDAQ index family when the KRX key has those services (코스닥 일별매매정보, KOSDAQ 시리즈
  일별시세정보; 코스닥 종목기본정보 for `krx-info`), and skip them with a warning when it doesn't.
  Yahoo cross-checks use `.KQ`. Benchmarks `kosdaq`, `kosdaq150`.
- A security's market is the endpoint its data came from (`KOSPI` / `KOSDAQ` / `ETF`), not KRX's
  `MKT_NM`, which also carries segment names such as "KOSDAQ GLOBAL".
- `top-market-cap` example and template: parameter `market` = `KOSPI` (default), `KOSDAQ` or `ALL`.
- Demo data: 6 KOSDAQ-like stocks and synthetic KOSDAQ / KOSDAQ 150 indices (the KOSPI and ETF
  demo series are unchanged). `krx-index --sample`.
- Checked: KRX's sample data in the real formats (KOSDAQ index levels match the published ones);
  the end-to-end check runs a KOSDAQ strategy with slippage, identical in C# and Python.
  **Not yet checked:** a full real KOSDAQ download against `verify`; the pre-2023 KOSDAQ tick
  table against a primary source.

## 0.0.8 — 2026-11-11

- **Faster daily update:** builds are reproducible byte for byte (fixed zip timestamps, unchanged
  files not rewritten) and data installs copy only files that changed.
- **`klean backtest --detach`** runs in the background; foreground runs show elapsed time; a
  running run is shown as "running" by `klean logs` and the GUI; Ctrl+C stops LEAN too.
- **GUI:** start an optimization from the project page, start JupyterLab for a project, rename
  and delete runs.
- **macOS (Apple Silicon), experimental:** the end-to-end check passes in CI (LEAN build,
  C# = Python, report, notebook); install steps in docs/user/1-install.md. Not hand-tested.
- **Project files:** CONTRIBUTING.md, SECURITY.md, issue and pull-request templates.
- **Korean:** beginner page (docs/ko/, linked from the English page) and README.ko.md.
- CI also runs on macOS; tests no longer assume unresolved temp paths or a case-sensitive file
  system.

## 0.0.7 — 2026-11-10

- Slippage stays off by default, and that is now visible: `klean backtest` prints
  `slippage: off … Switch it on with --parameter slippage_ticks 1` (or the ticks used) for
  strategies that read the parameter; the first-backtest guide, the strategies page, the README
  and the beginner page say how to switch it on.

## 0.0.6 — 2026-11-10

- **Slippage model** (`KrxSlippageModel`, C# and Python, identical results): each fill is N KRX
  ticks per share worse than the bar's price. Off by default (results unchanged); the templates
  and the example read the parameter `slippage_ticks`
  (`klean backtest P --parameter slippage_ticks 1`). `krx_initialize(..., slippage_ticks=N)`;
  new C# helper `KrxModels.Initialize(security, boards, commissionRate, slippageTicks)`.
- **`klean update`**: the daily routine in one command (keys from `~/.config/krx-lean.env`,
  `krx-lean all`, install into the workspace). The workspace remembers its data root.
- **`klean models status | update`**: projects keep their own copy of the KRX models; `klean
  backtest`, `doctor` and the GUI now say when a copy differs from the current models, and
  `models update` replaces it (the old copy is kept as `.bak`).
- The end-to-end check covers slippage (C# = Python) and the models commands. 7 new tests.

## 0.0.5 — 2026-11-10

Security and robustness fixes, and continuous integration.

- **API keys no longer appear in error messages.** data.go.kr takes its key in the URL, and
  connection errors quoted that URL: a failed `dividends` / `rights` download could print the
  key. Errors and logs are now redacted (`serviceKey=***`). If you shared such a log, reissue
  the data.go.kr key.
- `klean data install lean.zip` refuses zip entries that would be written outside the workspace.
- Run folders are unique even when two runs start in the same second (`…-2`).
- `klean backtest --timeout SECONDS` and `klean optimize --timeout SECONDS` stop LEAN after that
  long; the run is reported as failed.
- **CI** on GitHub Actions: lint and unit tests on Ubuntu 22.04 / 24.04 (Python 3.10, 3.12,
  3.13), and `tests/e2e-demo.sh`, an end-to-end check on the synthetic demo data (LEAN build,
  C# = Python parity, failure detection, optimize, report, research notebook).
- Tests: 37 pipeline + 39 klean.

## 0.0.4 — 2026-11-08

- `klean research`: JupyterLab no longer shows "news" and "new version" pop-ups or contacts
  jupyter.org for them; starter notebooks have cell ids (no nbformat warning).
- Docs revised throughout for 0.0.3–0.0.4: research in the README, the users track (install,
  workspace layout, strategies, tools, troubleshooting), the developers track (architecture,
  LEAN build versions, manual notebook steps, klean internals, a verification record on the
  demo data, roadmap) and the beginner page (a "notebook" step with a screenshot).

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
