# Try it without keys: synthetic demo data

> **SYNTHETIC DEMO DATA — NOT REAL MARKET DATA.** Every price, index level and dividend in the
> demo is made up by a random-number generator. The companies don't exist. Use it to learn
> klean while your KRX key is being approved; never draw conclusions about the Korean market
> from it.

The KRX Open API key can take a day to be approved. Meanwhile you can go through the whole
users track on a built-in demo data set, after [1. Install](1-install.md):

```bash
klean init ~/krx-demo --lean ~/Lean --python-venv ~/.klean/py311
cd ~/krx-demo
klean data install --demo          # ~10 s: generates, builds and installs the synthetic data
klean doctor
klean project-create Hold                           # buy and hold (the demo stock D00010)
klean project-create Top20 --template top-market-cap
klean backtest Hold
klean backtest Top20
klean report Top20
klean gui
klean research Top20                                # a Jupyter notebook on the demo data
```

Use a **separate workspace** for the demo (here `~/krx-demo`): klean refuses to put demo data
into a workspace with real data, and real data into a demo workspace, so the two never mix.
When your key arrives, follow [2. Keys and data](2-data.md) and create `~/krx-workspace` as in
[3. First backtest](3-first-backtest.md).

## What's in it

| | |
|---|---|
| Dates | 2011-01-03 → 2026-09-30, on LEAN's KRX trading calendar |
| Securities | 29 KOSPI-like stocks `D00010` … `D00280` (one preferred share `D00015`), 3 ETFs `E00010` … `E00030`; all named "SYNTHETIC DEMO …" |
| Indices | synthetic KOSPI and KOSPI 200 (`kospi`, `kospi200`), so benchmarks work |
| Events | a 5:1 split (D00020, 2018-05-04), a delisting (D00030, 2019-06-28), a new listing (D00040, 2015-06-01), yearly cash dividends |
| Prices | random walks: a market factor trending about 4% a year with ~17% volatility, plus noise per stock; prices on the KRX tick grid; the same every time |

The demo goes through the real pipeline: `krx_lean/demo.py` writes raw files in the KRX and
data.go.kr formats, and the normal build turns them into LEAN data. So templates, fees and
taxes, tick sizes, universes, factor files, delistings, optimization, reports and the GUI all
work as they will with real data.

## How you can tell

- Codes start with `D` or `E` (no real KRX code does); names say "SYNTHETIC DEMO".
- Every data folder has a `SYNTHETIC-DEMO-DATA.txt` file.
- `klean doctor` and `klean data status` say "SYNTHETIC DEMO DATA".
- `klean backtest`, `optimize` and `compare` print a `*** SYNTHETIC DEMO DATA … ***` banner;
  each run's `manifest.json` has `"synthetic_demo_data": true`.
- Reports are titled "… - SYNTHETIC DEMO DATA" and say so in the description.
- The GUI shows an orange banner on every page and a badge on demo runs.

Without keys, `krx-lean krx --sample` (KRX's public sample endpoint) is **not** a substitute: it
returns 10 rows per call, no KOSPI 200 index and a rotating handful of stocks, so no strategy
can run on it. It's only a smoke test for the download code (see the developers track).
