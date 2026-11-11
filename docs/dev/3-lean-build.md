# 3. LEAN build

| Component | Version |
|---|---|
| LEAN | `QuantConnect/Lean` commit `80e7843f645673bcbeaab963049f76f20f6785e1` (`klean/workspace.py: LEAN_COMMIT`) |
| .NET SDK | 10.0 (tested 10.0.401 and 10.0.403) |
| Python for LEAN | CPython **3.11** with a shared libpython; pandas 2.3.3, numpy 1.26.4 (LEAN's `DockerfileLeanFoundation` at that commit); matplotlib 3.8.4 for reports and notebooks; JupyterLab 4.5.1 and clr-loader 0.2.9 for notebooks (LEAN's Docker images) |
| Python for the tools | 3.10+ (tested 3.13) |

## Build by hand

```bash
git clone https://github.com/QuantConnect/Lean.git ~/Lean && cd ~/Lean
git checkout 80e7843f645673bcbeaab963049f76f20f6785e1
dotnet build Launcher/QuantConnect.Lean.Launcher.csproj -c Release     # ~2 min, warnings are normal
dotnet build Report/QuantConnect.Report.csproj -c Release              # only for reports
```

`klean install-lean` does the same with a shallow fetch of that commit. Output:
`Launcher/bin/Release/` (launcher, engine, LEAN's own example algorithm DLLs, and the research
parts: `QuantConnect.Research.dll`, `start.py`), `Report/bin/Release/`.

## Python 3.11 for pythonnet

LEAN loads Python through pythonnet with two environment variables:

```bash
export PYTHONNET_PYDLL=<path to libpython3.11.so>
export PYTHONPATH=<venv>/lib/python3.11/site-packages
```

`klean install-python` creates the venv from uv's CPython 3.11 (python-build-standalone, built
with `--enable-shared`, ships `lib/libpython3.11.so`) and records the library path
(`find_python_dll` in `klean/workspace.py`). Any CPython 3.11 with a shared library works
(Debian 12: `libpython3.11`; Ubuntu: deadsnakes PPA).

## macOS

CI runs the end-to-end script on `macos-latest` (Apple Silicon): LEAN builds with .NET 10 on
arm64, uv's CPython 3.11 provides `libpython3.11.dylib` (found by `find_python_dll`), and
backtests, the report and the research notebook pass with C# = Python identical. Two things
differ from Linux and matter for tests: temp folders sit behind a symlink (`/var` →
`/private/var`), so compare resolved paths; and the file system ignores case, so `Data/` and
`data/` are the same folder. Not hand-tested; Intel Macs untested.

## Updating LEAN

1. Build the new commit (`klean lean update --commit C`, which also rebuilds `Report` if it was
   built).
2. Rerun the reference backtests (top-market-cap in C# and Python) and `klean compare` them with
   runs on the previous commit.
3. Check the launcher's, report's and `start.py`'s config keys still match (`klean/backtest.py`,
   `klean/report.py`, `klean/research.py`) and that the package versions in LEAN's
   `DockerfileLeanFoundation` / `DockerfileJupyter` didn't change (update `PYTHON_PACKAGES`,
   `REPORT_PACKAGES`, `RESEARCH_PACKAGES` if they did); run `klean research P --execute`.
4. Update `LEAN_COMMIT` and this page; note it in the changelog.

## Things that differ from LEAN's Docker image

- No Docker: the launcher runs directly on the host; Python comes from the venv above.
- LEAN's `Optimizer.Launcher` starts backtests without a data folder or config of their own, so
  klean runs optimizations itself ([6. klean internals](6-klean.md)).
- LEAN's `Report` takes most settings only from `./config.json`; klean runs it in a scratch
  folder with a generated config.
- PDF reports: LEAN's image uses wkhtmltopdf + xvfb; klean uses wkhtmltopdf if present, else
  headless Chromium.
- Research: LEAN's research image runs Jupyter with `start.py` as an IPython startup file and a
  `config.json` in the notebook folder; klean runs the same `start.py` from a generated config
  (see [6. klean internals](6-klean.md#research)). Python notebooks only (no .NET Interactive).
