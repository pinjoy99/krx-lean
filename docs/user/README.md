# Users track

Write and test KOSPI/ETF strategies in Python or C# on your own machine, with `klean` doing the
setup and the runs.

1. [Install](1-install.md) — tools, .NET, LEAN, Python 3.11 (Linux, WSL2)
   - [Try it without keys](demo.md) — synthetic demo data, while your KRX key is approved
2. [Keys and data](2-data.md) — API keys, first download, building the LEAN data
3. [Workspace and first backtest](3-first-backtest.md)
4. [Writing strategies](4-strategies.md) — the KRX setup every strategy needs, Python and C#
5. [Optimize, report, compare, GUI](5-tools.md)
6. [Daily update](6-daily-update.md)
7. [Troubleshooting](7-troubleshooting.md)

Paths used throughout (change them if you like):

| Path | What |
|---|---|
| `~/krx-lean` | this repository (keep it: klean copies the KRX models from it) |
| `~/.krx-lean/venv` | the Python environment with the `krx-lean` and `klean` commands |
| `~/Lean` | LEAN, built from source |
| `~/.klean/py311` | Python 3.11 environment LEAN uses for Python strategies |
| `~/krx-data` | downloaded and built KRX data |
| `~/krx-workspace` | your workspace: projects and their results |
| `~/krx-demo` | a separate workspace for the [synthetic demo data](demo.md) (optional) |
