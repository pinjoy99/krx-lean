# 3. Workspace and first backtest

## Create the workspace

```bash
klean init ~/krx-workspace --lean ~/Lean --python-venv ~/.klean/py311
cd ~/krx-workspace
klean data install --root ~/krx-data      # LEAN data + KRX market hours and symbol properties
klean doctor                              # every line should say OK
klean data status                         # date range, securities, indices
```

A workspace is a folder with `klean.json` (settings) and `data/` (LEAN's data folder for this
workspace). Run `klean` commands inside it (or in any folder below it). `klean init` copies only
LEAN's configuration files, not LEAN's sample market data.

```
krx-workspace/
  klean.json                 lean_root, python_venv, python_dll, LEAN settings
  data/                      market hours, symbol properties, equity/krx, index/krx
  Top20/                     a project
    main.py  krx_models.py
    backtests/2026-11-02_10-15-00/    one folder per run
```

## Create a project and run it

```bash
klean project-create Top20 --template top-market-cap      # Python (default)
klean backtest Top20
```

Templates: `buy-hold` (default: buys Samsung Electronics), `top-market-cap` (the example
strategy: the 20 largest KOSPI common stocks, equal weight, rebalanced monthly), `empty`.
For C#: `klean project-create Top20CS --language csharp --template top-market-cap`.

What `backtest` does: checks (Python) or compiles (C#) the project, runs LEAN with the
workspace's data, and prints the main statistics. Results go to
`Top20/backtests/<date>_<time>/`:

| File | Content |
|---|---|
| `<Algorithm>-summary.json` | statistics |
| `<Algorithm>.json` | full result, with charts |
| `<Algorithm>-order-events.json` | orders and fills |
| `<Algorithm>-log.txt` | your `log()` lines |
| `console.txt` | LEAN's output: look here when something fails |
| `code/` | a copy of the project's files as they were for this run |
| `config.json`, `manifest.json` | the LEAN config used; what produced the run (krx-lean and LEAN versions, data date, parameters, file fingerprints) |

Python runs are slower than C# (about 2.5 min vs 20 s for the top-20 strategy over the full
data), and may end with a `GIL must always be released` message after the results are written;
that's harmless.

## Look at the results

```bash
klean logs Top20 --tail 20        # the algorithm's log
klean report Top20                # LEAN's HTML report → Top20/backtests/<run>/report.html
klean gui                         # charts, orders, code, reports in the browser
```

Next: [4. Writing strategies](4-strategies.md).
