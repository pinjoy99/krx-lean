# krx-lean

Korean stock market (KRX) data and market models for
[QuantConnect LEAN](https://github.com/QuantConnect/Lean), the open-source backtesting engine,
built from source on your own machine. Backtest KOSPI stocks and ETFs in Python or C#, with
KRX fees, taxes and tick sizes, the KOSPI 200 benchmark, daily universes including delisted
stocks, and prices adjusted for splits, rights issues and dividends; explore the data in Jupyter
notebooks with LEAN's QuantBook.

Everything runs locally: no Docker, no QuantConnect account, no cloud service. You download the
data yourself with your own free API keys.

```
KRX Open API ─┐                                 ┌─▶ Python strategies
data.go.kr  ──┴─▶ krx-lean (download → build) ──▶ LEAN (built from source)
                                                └─▶ C# strategies
        klean: workspace, projects, backtests, optimization, reports, notebooks, GUI
```

**Scope (0.0.x):** KOSPI stocks and ETFs, daily bars. Not covered: KOSDAQ, KONEX, NXT, minute
data, live trading.

**Platforms:** Linux (Ubuntu 24.04 / 22.04 tested) and Windows through WSL2. Other glibc Linux
distributions should work. macOS is not tested yet.

**New here?** The [beginner's guide](https://pinjoy99.github.io/krx-lean/) walks you from a
fresh computer to your first backtest and notebook in under an hour.

## Pick a track

| | [Users](docs/user/) | [Developers](docs/dev/) |
|---|---|---|
| For | writing and testing strategies | changing the data rules, the models or the tools |
| Works with | `klean` (one command per step) | the same steps by hand, plus the internals |
| Start at | [1. Install](docs/user/1-install.md) | [1. Architecture](docs/dev/1-architecture.md) |

## Quick look

No keys yet? `klean data install --demo` installs **synthetic** demo data (made-up prices,
clearly marked) so you can try everything first: [Try it without keys](docs/user/demo.md).

```bash
krx-lean --root ~/krx-data all                 # download KRX prices + dividends, build LEAN data
klean init ~/krx-workspace --lean ~/Lean --python-venv ~/.klean/py311
cd ~/krx-workspace && klean data install --root ~/krx-data
klean project-create Top20 --template top-market-cap
klean backtest Top20
klean report Top20
klean gui
klean research Top20                           # Jupyter notebook with LEAN's QuantBook
```

## What you need

- Linux or WSL2, about 5 GB of disk (LEAN build ~1 GB, data ~1 GB for 2010 onward, the Python
  3.11 environment ~0.5 GB with the notebook packages).
- git, Python 3.10+ for the tools, the .NET 10 SDK, and Python 3.11 for LEAN's Python
  strategies (installed for you by `klean install-python` via [uv](https://docs.astral.sh/uv/)).
- Free API keys: [KRX Open API](https://openapi.krx.co.kr/) (prices) and
  [data.go.kr](https://www.data.go.kr/) (dividends). See [2. Keys and data](docs/user/2-data.md).

## License and data

krx-lean is licensed under [Apache-2.0](LICENSE). It is not affiliated with QuantConnect or
Korea Exchange (see [NOTICE](NOTICE)). No market data is included: the data you download is
subject to the terms of each source (KRX Open API terms; data.go.kr 공공누리 terms; the optional
cross-check sources Yahoo Finance and aikstockdata.com are for personal, non-commercial use).
Don't redistribute it.

[Changelog](CHANGELOG.md)
