# 5. Manual workflow (without klean)

Everything klean automates, done with the pipeline and LEAN's launcher directly. Useful for
debugging, for scripting, and for seeing exactly what runs. Paths as in the users track; LEAN at
`~/Lean`, built as in [3. LEAN build](3-lean-build.md).

## Pipeline

```bash
cd ~/krx-lean && python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[crosscheck]'
set -a; . ~/.config/krx-lean.env; set +a
R=--root=$HOME/krx-data              # --root goes before the command name
krx-lean $R krx                      # KOSPI + ETF from 2010-01-04 (resumable)
krx-lean $R krx-index                # KOSPI index family
krx-lean $R krx-info                 # security master (optional)
krx-lean $R dividends                # 8 calls
krx-lean $R rights                   # ~126 calls, 15–25 min (optional)
krx-lean $R build                    # ohlcv/, lean/, securities.csv, factor files, universe (~2 min)
```

`krx-lean all` = `krx` + `krx-index` + `dividends` (if `DATA_GO_KR_KEY` is set) + `build`.

## Data into LEAN

Into LEAN's own data folder (what LEAN uses when no `--data-folder` is given):

```bash
krx-lean $R lean-install ~/Lean/Data          # rerun after every build
```

Or into a separate data folder (what a klean workspace's `data/` is): copy LEAN's
`Data/market-hours` and `Data/symbol-properties` there first, then `lean-install` into it.
Idempotent; adds and replaces files, never deletes.

## C# algorithm

```bash
cp examples/KrxModels.cs examples/KrxTopMarketCapAlgorithm.cs ~/Lean/Algorithm.CSharp/
cd ~/Lean && dotnet build Launcher/QuantConnect.Lean.Launcher.csproj -c Release
cd Launcher/bin/Release
dotnet QuantConnect.Lean.Launcher.dll --algorithm-type-name KrxTopMarketCapAlgorithm \
  --algorithm-language CSharp --algorithm-location QuantConnect.Algorithm.CSharp.dll \
  --data-folder ~/Lean/Data/ --close-automatically true
```

Rebuild after every `.cs` change (not after data changes). klean instead builds each project as
its own DLL against the launcher's DLLs (`-p:LeanBin=…`, excluding LEAN's own
`QuantConnect.Algorithm.CSharp.dll`), so LEAN's tree stays untouched.

## Python algorithm

```bash
mkdir -p ~/strategies/top20
cp examples/python/krx_top_market_cap/main.py examples/python/krx_models.py ~/strategies/top20/
export PYTHONNET_PYDLL=$(ls ~/.local/share/uv/python/cpython-3.11*/lib/libpython3.11.so | head -1)
export PYTHONPATH=$HOME/.klean/py311/lib/python3.11/site-packages
cd ~/Lean/Launcher/bin/Release
dotnet QuantConnect.Lean.Launcher.dll --algorithm-type-name KrxTopMarketCapAlgorithm \
  --algorithm-language Python --algorithm-location ~/strategies/top20/main.py \
  --data-folder ~/Lean/Data/ --close-automatically true
```

No rebuild for Python changes. The process may abort at exit with `GIL must always be
released …` after writing results; read `<Algorithm>-summary.json` rather than trusting the exit
code.

## Results

In `Launcher/bin/Release/` (or `--results-destination-folder DIR`):
`<Algorithm>-summary.json` (statistics), `<Algorithm>.json` (charts), `-order-events.json`,
`-log.txt`, `failed-data-requests-*.txt`. For universe strategies, `failed-data-requests` lists
`universe/<date>.zip` for weekends and holidays (expected); any `daily/`, `factor_files/` or
`map_files/` entry means missing data.

## Other launcher options klean uses

`--config FILE` (a full LEAN config; klean writes one per run with the sample `parameters`
removed), `--parameters k:v,k2:v2`, `--backtest-name`, `--results-destination-folder`.
LEAN's `config.json` contains comments and trailing commas; strip them before parsing it as JSON.

## A notebook by hand

What `klean research` sets up, by hand (JupyterLab 4.5.1, ipykernel and clr-loader 0.2.9
installed into the 3.11 env first):

```bash
mkdir -p ~/research && cd ~/research
cat > config.json <<END
{"data-folder": "$HOME/Lean/Data/", "composer-dll-directory": "$HOME/Lean/Launcher/bin/Release/",
 "algorithm-language": "Python", "messaging-handler": "QuantConnect.Messaging.Messaging",
 "job-queue-handler": "QuantConnect.Queues.JobQueue", "api-handler": "QuantConnect.Api.Api"}
END
export DOTNET_ROOT=$HOME/.dotnet PYTHONNET_PYDLL=…/libpython3.11.so
export PYTHONPATH=$HOME/Lean/Launcher/bin/Release
~/.klean/py311/bin/python -m jupyter lab
```

In a notebook in that folder, the first cell is `%run ~/Lean/Launcher/bin/Release/start.py`,
then `qb = QuantBook()`. Keep notebooks next to that `config.json`: `QuantBook()` re-reads
`./config.json` (klean avoids this by pointing LEAN at its config file's absolute path).

## A report by hand

```bash
cd ~/Lean/Report/bin/Release        # it reads template.html, css/, ReportCharts.py from the current folder
cat > config.json <<EOF
{"data-folder": "$HOME/Lean/Data/", "backtest-data-source-file": "/path/to/Algo.json",
 "report-destination": "/tmp/report.html", "strategy-name": "Top20", "close-automatically": true}
EOF
PYTHONNET_PYDLL=… PYTHONPATH=… dotnet QuantConnect.Report.dll
```
