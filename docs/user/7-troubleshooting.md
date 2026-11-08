# 7. Troubleshooting

Start with `klean doctor` (inside the workspace). When a backtest fails, read the lines klean
prints and `console.txt` in the run folder (`klean logs PROJECT --console`).

## Setup

| Message | Fix |
|---|---|
| `dotnet not found` | install the .NET 10 SDK and add `~/.dotnet` to `PATH` ([1. Install](1-install.md)) |
| .NET: `Couldn't find a valid ICU package` | `sudo apt install -y libicu-dev` |
| `no Python 3.11` | install uv, then `klean install-python` again |
| `no shared libpython3.11` | use uv's Python (`klean install-python` without `--python`) |
| `no klean.json in … or its parents` | run inside the workspace, or `klean init` |
| `no LEAN build in …` | `klean install-lean --dir ~/Lean`, or fix `lean_root` with `klean config set` |
| `no Python environment in klean.json` | `klean config set python_venv ~/.klean/py311` |

## Data

| Message | Fix |
|---|---|
| `KRX_API_KEY is not set` | load the key file: `set -a; . ~/.config/krx-lean.env; set +a` |
| `401 Unauthorized Key` | the key is wrong (typo, extra characters) |
| `401 Unauthorized API Call` | that KRX service isn't approved yet |
| `DATA_GO_KR_KEY not set: no dividends` | add the data.go.kr key; prices are otherwise not dividend-adjusted |
| data.go.kr errors on a new key | wait an hour; use the *Decoding* key |
| `network error, stopping (re-run the same command to resume)` | a timeout or dropped connection: run the same command again; days already downloaded are kept |
| `krx --sample` data can't run any template | expected: KRX's sample endpoint has no KOSPI 200 and only a few rotating stocks; use the [synthetic demo](demo.md) instead |
| the latest trading day is missing | KRX publishes the next day; rerun later |
| `klean data status` shows an old `last_date` | run `klean data install --root ~/krx-data` after `krx-lean all` |

## Backtests

| Message (in the output or console.txt) | Fix |
|---|---|
| `backtest FAILED …` | the algorithm stopped with an error, shown right after; fix it (or the data) and run again |
| `no kospi200 index data at …` | the workspace has no KRX index data: `krx-lean --root ~/krx-data krx-index` (needs the KRX key), then `klean data install --root ~/krx-data`; or try the [demo](demo.md) |
| `doctor`: `KOSPI 200 index (benchmark)` NO | same as above |
| `… holds SYNTHETIC demo data` / `… already has real KRX data` | demo and real data never share a workspace: use `~/krx-demo` for the demo and `~/krx-workspace` for real data |
| `unexpected equity Market krx` | the strategy has no KRX fee model: keep `krx_initialize` / `KrxFeeModel` |
| market hours not found for `Equity-krx` | `klean data install …` wasn't run in this workspace |
| `No module named krx_models` | keep `krx_models.py` next to `main.py` |
| `No module named …` (another package) | add it to the project's `requirements.txt` |
| `expected one class deriving from QCAlgorithm` | keep exactly one algorithm class per project |
| alpha and beta are 0 | use `krx_benchmark(...)` / `KrxIndex.Benchmark(...)`, not an index symbol |
| `GIL must always be released` stack trace at the end of a Python run | harmless: pythonnet's shutdown, after the results are written (klean says so) |
| C# compile errors | read them in the output; they name the file and line |
| WSL: very slow runs | move the workspace out of `/mnt/c` into `~` |
| WSL: optimization processes killed | raise WSL's memory (`.wslconfig`) or use fewer `--max-concurrent-backtests` |

## Reports, research and GUI

| Message | Fix |
|---|---|
| `report.html already exists` | `--overwrite` |
| `this run failed, so there's nothing to report` | run the backtest successfully first |
| `--pdf needs wkhtmltopdf or Chromium` | `sudo apt install -y wkhtmltopdf` (the HTML report is written anyway) |
| report fails | read `report-console.txt` next to the report |
| `klean research`: `LEAN's research files aren't in …` | rebuild LEAN: `klean lean update` |
| `klean research`: the notebook says `QuantBook` isn't defined | the kernel didn't load LEAN: start Jupyter with `klean research` (not plain `jupyter lab`); see `.klean/research/log.txt` |
| `klean research`: `port … is already in use` | another Jupyter is running: stop it, or `--port` another number |
| GUI: `403` | open the full URL klean printed (it has the token) |
| WSL: the browser doesn't open | `sudo apt install -y wslu`, or open the printed URL yourself |
