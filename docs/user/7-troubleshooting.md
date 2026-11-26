# 7. Troubleshooting

Start with `klean doctor` (inside the workspace). When a backtest fails, read the lines klean
prints and `console.txt` in the run folder (`klean logs PROJECT --console`).

## Setup

| Message | Fix |
|---|---|
| `dotnet not found` | install the .NET 10 SDK and add `~/.dotnet` to `PATH` ([1. Install](1-install.md)) |
| .NET: `Couldn't find a valid ICU package` | `sudo apt install -y libicu-dev` |
| `no Python 3.11` | install uv, then `klean install python` again |
| `no shared libpython3.11` | use uv's Python (`klean install python` without `--python`) |
| `no klean.json in … or its parents` | run inside the workspace, or `klean init` |
| `no LEAN build in …` | `klean install lean --dir ~/Lean`, or fix `lean_root` with `klean config set` |
| `no Python environment in klean.json` | `klean config set python_venv ~/.klean/py311` |

## Data

| Message | Fix |
|---|---|
| `KRX_API_KEY is not set` | load the key file: `set -a; . ~/.config/krx-lean.env; set +a` |
| `401 Unauthorized Key` | the key is wrong (typo, extra characters) |
| `401 Unauthorized API Call` | that KRX service isn't approved yet |
| `KOSDAQ price skipped: this service isn't approved for your KRX key` | not an error: KOSPI and ETFs are complete. For KOSDAQ, approve 코스닥 일별매매정보 and KOSDAQ 시리즈 일별시세정보, then run the update again |
| `DATA_GO_KR_KEY not set: no dividends` | add the data.go.kr key; prices are otherwise not dividend-adjusted |
| data.go.kr errors on a new key | wait an hour; use the *Decoding* key |
| `network error, stopping (re-run the same command to resume)` | a timeout or dropped connection: run the same command again; days already downloaded are kept |
| `krx --sample` data can't run any template | expected: KRX's sample endpoint has no KOSPI 200 and only a few rotating stocks; use the [synthetic demo](demo.md) instead |
| the latest trading day is missing | KRX publishes the next day; rerun later |
| `klean status data` shows an old `last_date` | run `klean update data` (or `klean install data --root ~/krx-data` after `krx-lean all`) |
| `no data root known for this workspace` | `klean update data --root ~/krx-data` once; it's remembered |

## Backtests

| Message (in the output or console.txt) | Fix |
|---|---|
| `backtest FAILED …` | the algorithm stopped with an error, shown right after; fix it (or the data) and run again |
| `no kospi200 index data at …` | the workspace has no KRX index data: `krx-lean --root ~/krx-data krx-index` (needs the KRX key), then `klean install data --root ~/krx-data`; or try the [demo](demo.md) |
| `doctor`: `KOSPI 200 index (benchmark)` NO | same as above |
| `… holds SYNTHETIC demo data` / `… already has real KRX data` | demo and real data never share a workspace: use `~/krx-demo` for the demo and `~/krx-workspace` for real data |
| `note: …/krx_models.py differs from krx-lean's current KRX models` | the project has an older (or edited) copy of the models: `klean update models NAME` ([6. Daily update](6-daily-update.md#after-updating-krx-lean-itself)) |
| `unexpected equity Market krx` | the strategy has no KRX fee model: keep `krx_initialize` / `KrxFeeModel` |
| market hours not found for `Equity-krx` | `klean install data …` wasn't run in this workspace |
| `No module named krx_models` | keep `krx_models.py` next to `main.py` |
| `No module named …` (another package) | add it to the project's `requirements.txt` |
| `expected one class deriving from QCAlgorithm` | keep exactly one algorithm class per project |
| alpha and beta are 0 | use `krx_benchmark(...)` / `KrxIndex.Benchmark(...)` with an index (`"kospi200"`) or a stock code (`"005930"`), not `set_benchmark("005930")` or an index symbol (LEAN asks for hourly benchmark data; KRX data is daily) |
| `GIL must always be released` stack trace at the end of a Python run | harmless: pythonnet's shutdown, after the results are written (klean says so) |
| C# compile errors | read them in the output; they name the file and line |
| WSL: very slow runs | move the workspace out of `/mnt/c` into `~` |
| `klean logs` says `STILL RUNNING` | a `--detach` run (or one started from the GUI) hasn't finished; `tail -f <run>/klean-detached.log` follows it |
| a backtest never finishes | a loop in the strategy, or a very long run: stop it with Ctrl+C, or run with `--timeout SECONDS` |
| `timed out after … s (--timeout)` | the run was stopped by your `--timeout`; raise it or speed the strategy up |
| `lean.zip: entry … would be written outside …` | the zip isn't a krx-lean data package (`krx-lean lean-package`); nothing was unzipped |
| WSL: optimization processes killed | raise WSL's memory (`.wslconfig`) or use fewer `--max-concurrent-backtests` |

## Reports, research and GUI

| Message | Fix |
|---|---|
| `report.html already exists` | `--overwrite` |
| `this run failed, so there's nothing to report` | run the backtest successfully first |
| `--pdf needs wkhtmltopdf or Chromium` | `sudo apt install -y wkhtmltopdf` (the HTML report is written anyway) |
| report fails | read `report-console.txt` next to the report |
| `klean research`: `LEAN's research files aren't in …` | rebuild LEAN: `klean update lean` |
| `klean research`: the notebook says `QuantBook` isn't defined | the kernel didn't load LEAN: start Jupyter with `klean research` (not plain `jupyter lab`); see `.klean/research/log.txt` |
| `klean research`: `port … is already in use` | another Jupyter is running: stop it, or `--port` another number |
| GUI: `403` | open the full URL klean printed (it has the token) |
| WSL: the browser doesn't open | `sudo apt install -y wslu`, or open the printed URL yourself |

## Live paper trading

`klean live status` shows each deployment's state; a failed day's console is in
`<project>/live/<id>/runs/<day>/console.txt` (and under *Daily runs* on the Live dashboard).

| Message | Fix |
|---|---|
| `…'s copy of the KRX models is … not krx-lean's current one` (at deploy) | `klean update models NAME`, then deploy again; `--models-as-is` only for a copy you edited on purpose |
| `waiting for data` | normal for a new deployment: it trades after the next `klean update data` |
| `… FAILED: the strategy got no data for this day` | the strategy subscribed to nothing at daily resolution, or its models copy is old: update the models and deploy again. The account was left as it was; the day is retried on the next run |
| `… FAILED: …` (another error) | the strategy raised an error on that day (the message is the strategy's); fix it and deploy again. The day is retried, the account is unchanged |
| edits to the strategy don't change a deployment | expected: a deployment keeps the code and parameters it was deployed with. Stop it and deploy again |
| `KIS_PAPER_APP_KEY, … not set` | put the 모의투자 account's keys in `~/.config/krx-lean.env` ([5. Tools](5-tools.md#kis-paper-a-korea-investment-모의투자-paper-account)) |
| `KIS_APP_KEY, …: klean now reads only KIS-PAPER keys` | rename the keys in `~/.config/krx-lean.env` to `KIS_PAPER_APP_KEY`, `KIS_PAPER_APP_SECRET`, `KIS_PAPER_ACCOUNT` and remove `KIS_MOCK` |
| `KIS EGW…` / `KIS OPSQ…` / other `KIS` codes | KIS's own message follows the code; check the keys with `klean live kis-check`. They must be the **모의투자** account's keys (real-account keys don't work on the 모의투자 server) |
| `… (KIS-PAPER): orders go out during the pre-open auction …: skipped` | not an error: the run was outside 08:30–08:59 KST or not on a trading day. `--now` runs anyway (orders then fill at once) |
| `… already trades this KIS account` | one 모의투자 account serves one strategy: stop the other deployment, or use another account |
| `a KIS-PAPER deployment can't be backdated` | leave out `--start`; backdated tests run on klean's own paper broker |
| `… skipped, already being run by pid …` | not an error: another klean process (a schedule, `klean update data`, the GUI) is trading this deployment's new days right now; it does the work |
| `… stops after the day being processed now` | *Stop* came while a run was busy: it stops when the current trading day is done |
| `waiting for pid … (another package install)` / `(building the live plugin)` / `(the data)` | another klean process is installing packages, building the plugin or using the data: this one goes on when it's done |
| `warning: file locks don't work in …` | the workspace is on a drive without file locks (possibly `/mnt/c` under WSL), so klean can't keep its processes apart there: move it into your Linux home folder (`~`) |
| `… (in /other/workspace) already trades this KIS account` / `… trades this account now: not run` | a deployment in another klean workspace trades this 모의투자 account: stop one of them |
