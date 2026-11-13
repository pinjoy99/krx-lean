# 4. Writing strategies

A project is a folder in the workspace. Python: `main.py` (one class deriving from
`QCAlgorithm`), `krx_models.py`, any other `.py` files, and optionally `requirements.txt`
(installed into the Python 3.11 environment before each run). C#: `Main.cs`, `KrxModels.cs` and
a `.csproj` referencing your LEAN build. Start from a template (`klean create project`) and edit
`main.py` / `Main.cs` in any editor.

LEAN's own documentation covers the API (orders, indicators, scheduling, universes):
<https://www.quantconnect.com/docs/v2/writing-algorithms>. This page covers what's specific to
KRX. To look at the data before writing code (prices, indicators, charts), use a notebook:
`klean research PROJECT` ([5. Tools](5-tools.md#research-notebooks)).

## The setup every KRX strategy needs

### Python

```python
from AlgorithmImports import *
from krx_models import KOSPI, KrxBoards, KrxUniverseData, krx_benchmark, krx_initialize


class MyStrategy(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2026, 9, 30)             # set one: without it, yearly figures change daily
        self.set_cash(100_000_000)                 # won
        self.set_time_zone("Asia/Seoul")
        self.set_account_currency("KRW")
        boards = KrxBoards.load()                  # code → KOSPI / ETF, from data/equity/krx/securities.csv
        self.set_security_initializer(lambda s: krx_initialize(s, boards))   # KRX fees, taxes, tick sizes
        self.set_benchmark(krx_benchmark("kospi200"))
        self.add_equity("005930", Resolution.DAILY, Market.KRX)
```

`krx_initialize(security, boards, commission_rate=0.00015, slippage_ticks=0)`: set your broker's
commission, and slippage (below).

### C#

```csharp
SetTimeZone("Asia/Seoul");
SetAccountCurrency("KRW");
var boards = KrxBoards.Load();
SetSecurityInitializer(s => KrxModels.Initialize(s, boards));   // KRX fees, taxes, tick sizes
// options: KrxModels.Initialize(s, boards, commissionRate: 0.00015m, slippageTicks: 1)
SetBenchmark(KrxIndex.Benchmark("kospi200"));
AddEquity("005930", Resolution.Daily, Market.KRX);
```

## Universes (choosing stocks each day)

The data has one universe file per trading day with every listed security, **including stocks
that were later delisted** (no survivorship bias): code, market, close, volume, trading value,
market cap, listed shares.

```python
self.add_universe(KrxUniverseData, SecurityType.EQUITY, "kospi-top", Resolution.DAILY,
                  Market.KRX, self.select)

def select(self, data):
    stocks = [d for d in data if d["board"] == KOSPI and d.symbol.value.endswith("0")]   # common shares
    stocks.sort(key=lambda d: d["market_cap"], reverse=True)
    return [d.symbol for d in stocks[:20]]
```

The selection sees the **previous trading day's** values. Liquidate securities that leave the
universe yourself (`on_securities_changed`). The `top-market-cap` template is a complete
example in both languages.

## KRX rules the models apply

- **Codes and market:** always `Market.KRX` and 6-character codes (`"005930"`; letters occur,
  e.g. `"0052D0"`). KOSPI stocks, KOSDAQ stocks and ETFs are all added the same way; the models
  look up each code's market (`boards`) for its tax and tick size. In universes, `d["board"]` is
  `KOSPI`, `KOSDAQ` or `ETF`.
- **Fees:** commission (default 0.015% per side) plus the sell-side tax by settlement date
  (T+2): KOSPI 0.30% before June 2019, then 0.25%, 0.23% (2021), 0.20% (2023), 0.18% (2024), 0.15%
  (2025), 0.20% (2026); KOSDAQ the same totals; ETFs exempt. Fees are truncated to whole won. Without the fee model
  LEAN stops with `unexpected equity Market krx` at the first order.
- **Tick sizes** for limit and stop prices, by price band (the 2023 table and the earlier one);
  ETFs 5 won. LEAN rounds your prices to them.
- **Prices are adjusted** for splits, rights and bonus issues, capital reductions and cash
  dividends by default. Use `DataNormalizationMode.RAW` to trade at exchange prices (tick
  rounding is exact only then).
- **Benchmark:** use `krx_benchmark("kospi200")` / `KrxIndex.Benchmark("kospi200")` (or
  `"kospi"`; with KOSDAQ data `"kosdaq"`, `"kosdaq150"`), not an index symbol: an index symbol gives an empty benchmark (alpha and beta 0).
- **Delistings:** LEAN closes positions on a security's last trading day.
- **Common vs preferred:** codes ending in `0` are common shares (KRX convention);
  `securities.csv` has `share_class` if you ran `krx-info`.

## KOSDAQ

KOSDAQ is included when your KRX key has the KOSDAQ services ([2. Keys and data](2-data.md));
`klean status data` then lists KOSDAQ among the markets. The `top-market-cap` template takes a
`market` parameter: `KOSPI` (default), `KOSDAQ`, or `ALL` (both), and uses the KOSDAQ index as
benchmark for `KOSDAQ`:

```bash
klean backtest Top20 --parameter market KOSDAQ --parameter slippage_ticks 2
```

KOSDAQ support is new. Its data goes through the same rules as KOSPI, and the models give
identical results in C# and Python, but two things deserve care: small KOSDAQ stocks are far
less liquid (use slippage, and distrust results that depend on tiny stocks), and the KOSDAQ tick
table before 2023 isn't verified from a primary source (it only affects limit and stop prices
and slippage before 2023-01-25).

## Slippage

**Slippage is off by default**, and you can switch it on per run or per strategy. Without it
every order fills exactly at the daily bar's price, which is better than you'd get in the
market. `slippage_ticks` makes each fill worse by that many KRX ticks per share (buys higher,
sells lower). In code:

```python
self.set_security_initializer(lambda s: krx_initialize(s, boards, slippage_ticks=1))
```

The templates already read it as a parameter, so you can switch it on from the command line,
without editing code, and see what it costs:

```bash
klean backtest Top20 --parameter slippage_ticks 1 --backtest-name slip1
klean compare Top20 Top20/<the run without slippage>
```

One tick is about half the bid-ask spread of a liquid stock plus a little impact: a reasonable
minimum for large caps. Use more for small or thinly traded stocks, and distrust any strategy
whose profit disappears at 1–2 ticks. To have it on for every run of a strategy, change the
default in its code (`"0"` → `"1"` in the `slippage_ticks` line, or pass `slippage_ticks=1`).
The default stays off so that results are comparable with earlier runs. It is a fixed cost per
share and doesn't grow with your order's size (no market
impact model).

## Not modelled (yet)

Market impact (slippage that grows with order size); ±30% daily price limits and the
opening/closing auctions; T+2 cash settlement (sale proceeds are usable at once); short-selling
rules. LEAN's "Estimated Strategy
Capacity" shows ₩0 / "-" for KRX backtests; ignore it. Keep these in mind for small caps and
high turnover.

## Parameters

Read parameters in the algorithm, then set them per run (or search them, see
[5. Tools](5-tools.md)):

```python
self.holdings = int(self.get_parameter("holdings", "20"))
```

```bash
klean backtest Top20 --parameter holdings 25 --backtest-name h25
```

## Python or C#?

Both give identical results with the same strategy and data (checked to the won). Python is
easier to start with; C# runs several times faster, which matters for universe strategies over
many years and for optimizations. LEAN's Python API uses `snake_case`; its C# API `PascalCase`.

Next: [5. Tools](5-tools.md).
