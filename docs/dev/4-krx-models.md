# 4. KRX models

`examples/KrxModels.cs` (C#, namespace `QuantConnect.Algorithm.CSharp`) and
`examples/python/krx_models.py` implement the same rules. klean copies them into each new
project; a strategy uses them as shown in [user 4. Writing strategies](../user/4-strategies.md).

| C# | Python | What |
|---|---|---|
| `KrxBoards` | `KrxBoards` | code → market (KOSPI / KOSDAQ / KONEX / ETF), from `equity/krx/securities.csv` |
| `KrxFeeModel` | `KrxFeeModel` (via `krx_initialize`) | commission + sell-side tax |
| `KrxPriceVariationModel` | `KrxPriceVariationModel` (via `krx_initialize`) | tick sizes |
| `KrxUniverseData` | `KrxUniverseData` | the daily universe files |
| `KrxIndex.Benchmark` | `krx_benchmark` | KOSPI / KOSPI 200 as a benchmark function |

## Sell-side tax

By **settlement date** (T+2 on the exchange calendar), the basis the law uses (the 2025 cut
applied to trades from 2024-12-27, settling 2025-01-02). KOSPI totals include 농어촌특별세 0.15%;
ETFs are exempt.

| From (settlement) | KOSPI (거래세 + 농특세) | KOSDAQ | KONEX |
|---|---|---|---|
| before 2019-06-03 | 0.15% + 0.15% = 0.30% | 0.30% | 0.30% |
| 2019-06-03 | 0.10% + 0.15% = 0.25% | 0.25% | 0.10% |
| 2021-01-01 | 0.08% + 0.15% = 0.23% | 0.23% | 0.10% |
| 2023-01-01 | 0.05% + 0.15% = 0.20% | 0.20% | 0.10% |
| 2024-01-01 | 0.03% + 0.15% = 0.18% | 0.18% | 0.10% |
| 2025-01-01 | 0.00% + 0.15% = 0.15% | 0.15% | 0.10% |
| 2026-01-01 | 0.05% + 0.15% = 0.20% | 0.20% | 0.10% |

Sources (news and broker notices, cross-checked): 2019 — 시사저널e, 서울신문, 이투데이 (2019-05);
2021 — 한국세정신문; 2023–2025 — 헤럴드경제, 대신증권 and KB증권 notices; 2026 — 머니투데이,
한국세정신문 (2025-12). Commission: 0.015% per side by default (a constructor / `krx_initialize`
argument). Fees and taxes are truncated to whole won.

## Tick sizes

From 2023-01-25, one table for KOSPI/KOSDAQ/KONEX: < 2,000 → 1; < 5,000 → 5; < 20,000 → 10;
< 50,000 → 50; < 200,000 → 100; < 500,000 → 500; else 1,000. Before (from October 2010), KOSPI:
< 1,000 → 1; < 5,000 → 5; < 10,000 → 10; < 50,000 → 50; < 100,000 → 100; < 500,000 → 500; else
1,000. ETFs: 5 won. **Not verified from a primary source:** KOSDAQ/KONEX before 2023 (same up to
50,000, then 100), and January–October 2010 (the post-October table is used).

## Benchmark

LEAN subscribes a security benchmark at hourly resolution; with daily index data that benchmark
is empty (alpha 0, beta 0). `KrxIndex.Benchmark` / `krx_benchmark` read the daily index file and
return the last close on or before the time asked, as a benchmark function.

## Changing the models

The two files must stay equivalent. Change both, then run the parity check below.

| Change | Where |
|---|---|
| commission rate | argument only, no code change |
| a new tax rate | `KospiTax` / `KosdaqTax` / `KonexTax` in `KrxModels.cs` and `_KOSPI_TAX` / … in `krx_models.py`; add the source to this page |
| a new tick table | `KrxPriceVariationModel.Tick` and `tick_size()` |
| a new universe column | `lean_extras.build_universe`, then both `KrxUniverseData` readers |

Python implementation notes:
- **Fees use `Decimal`.** With floats, truncating to whole won drifted by a few won from C#.
- **`KrxPriceVariationModel` subclasses `SecurityPriceVariationModel`** with
  `__namespace__ = "QcKrx"` and also binds `GetMinimumPriceVariation`; without both, LEAN never
  called the Python method and limit prices weren't rounded. (The namespace string is internal to
  pythonnet; keep it unchanged.)
- **Universe rows store fields by key** (`row["market_cap"]`).

Both example algorithms log `CHECK tax …` and `CHECK tick …` lines with model values for known
dates; compare them after a change.

## Parity check (C# = Python)

```bash
klean project-create P --template top-market-cap
klean project-create C --language csharp --template top-market-cap
klean backtest P && klean backtest C
klean compare P C              # must print IDENTICAL (statistics and equity curves)
```

Last measured (2026-10, LEAN `80e7843`): identical end equity, fees, orders and equity curves;
C# ~20 s, Python ~2.5 min. Reports of the two runs are identical too (text and all charts).

## Not modelled

Slippage and market impact; ±30% price limits, auctions and VI (fill model); T+2 cash
settlement; a `KrxBrokerageModel` (order types, short-selling rules); late opens (first trading
day of the year, 수능일). LEAN's "Estimated Strategy Capacity" is ₩0 for KRX backtests (not
investigated).
