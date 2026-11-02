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
| `git clone` asks for a password | the repository is private: `gh auth login`, or a personal access token |

## Data

| Message | Fix |
|---|---|
| `KRX_API_KEY is not set` | load the key file: `set -a; . ~/.config/krx-lean.env; set +a` |
| `401 Unauthorized Key` | the key is wrong (typo, extra characters) |
| `401 Unauthorized API Call` | that KRX service isn't approved yet |
| `DATA_GO_KR_KEY not set: no dividends` | add the data.go.kr key; prices are otherwise not dividend-adjusted |
| data.go.kr errors on a new key | wait an hour; use the *Decoding* key |
| the latest trading day is missing | KRX publishes the next day; rerun later |
| `klean data status` shows an old `last_date` | run `klean data install --root ~/krx-data` after `krx-lean all` |

## Backtests

| Message (in the output or console.txt) | Fix |
|---|---|
| `unexpected equity Market krx` | the strategy has no KRX fee model: keep `krx_initialize` / `KrxFeeModel` |
| market hours not found for `Equity-krx` | `klean data install …` wasn't run in this workspace |
| `No module named krx_models` | keep `krx_models.py` next to `main.py` |
| `No module named …` (another package) | add it to the project's `requirements.txt` |
| `expected one class deriving from QCAlgorithm` | keep exactly one algorithm class per project |
| alpha and beta are 0 | use `krx_benchmark(...)` / `KrxIndex.Benchmark(...)`, not an index symbol |
| `GIL must always be released` at the end of a Python run | harmless (results are written) |
| C# compile errors | read them in the output; they name the file and line |
| WSL: very slow runs | move the workspace out of `/mnt/c` into `~` |
| WSL: optimization processes killed | raise WSL's memory (`.wslconfig`) or use fewer `--max-concurrent-backtests` |

## Reports and GUI

| Message | Fix |
|---|---|
| `report.html already exists` | `--overwrite` |
| `--pdf needs wkhtmltopdf or Chromium` | `sudo apt install -y wkhtmltopdf` (the HTML report is written anyway) |
| report fails | read `report-console.txt` next to the report |
| GUI: `403` | open the full URL klean printed (it has the token) |
| WSL: the browser doesn't open | `sudo apt install -y wslu`, or open the printed URL yourself |
