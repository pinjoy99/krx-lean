# 2. Data pipeline

## Sources

| Source | Endpoint | Coverage | Role |
|---|---|---|---|
| KRX Open API — daily trading | `https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd` (KOSPI), `etp/etf_bydd_trd` (ETF); also `ksq_…`, `knx_…` (KOSDAQ, KONEX; out of scope) | every listed security, one market per call, per date, from 2010-01-04; includes delisted securities | **only source of daily bars** |
| KRX Open API — indices | `idx/kospi_dd_trd` (also `krx_dd_trd`, `kosdaq_dd_trd`) | every index of the family per date, from 2010-01-04 | KOSPI, KOSPI 200 for benchmarks |
| KRX Open API — security master | `sto/stk_isu_base_info` | ISIN, listing date, share class, par value | optional fields in `securities.csv` |
| data.go.kr 금융위원회_주식배당정보 (15043284) | `apis.data.go.kr/1160100/GetStocDiviInfoService_V2/getDiviInfo_V2` | ~72k dividend records since 1985, one table, no date filter | price factors |
| data.go.kr 금융위원회_주식권리일정정보 (15059609) | `apis.data.go.kr/1160100/GetStocRighScheService_V2/getRighExerReasSche_V2` | ~1.26M rows, corporate-action dates since 2010; date filters ignored | `corporate_actions.csv` (research only) |
| Yahoo Finance via `yfinance` ≥ 0.2.54 | `{code}.KS` | daily bars, split-adjusted by Yahoo | cross-check only (`[crosscheck]` extra) |
| aikstockdata.com | static JSON/CSV under `/data/public/` | ~2,800 stocks, close/volume since 2020, OHLCV for 30 days; no ETFs, no delisted | cross-check only |

Keys: `KRX_API_KEY` (header `AUTH_KEY`, per-service approval), `DATA_GO_KR_KEY` (Decoding key),
from the environment only, whitespace stripped. data.go.kr takes its key as the URL parameter
`serviceKey`, and HTTP error messages quote the URL, so every error and log line goes through
`client.redact` (`serviceKey=***`, and the key values themselves, plain or URL-encoded).

## Downloads

- **KRX:** one call per (market, weekday) → `raw/krx/{MARKET}/{YYYY}/{YYYYMMDD}.csv.gz`, every
  field as returned (strings). Indices → `raw/krx_index/…`, master → `raw/krx_info/{MARKET}/…`.
- **Skip rule:** a date on disk is never requested again. A non-trading day is stored as an
  empty file, **except** within the last 7 days (KRX publishes the next day; 2026-10-07 was
  missing at 01:23 KST on 10-08 and present at 13:58 KST).
- **Errors:** the run stops at the first API error (bad key, unapproved service, quota) so a
  rerun resumes. HTTP 200 responses that aren't JSON (KRX error pages) are retried 3 times.
  Transport errors that outlast the client's retries (timeouts, dropped connections) end every
  download command with `network error, stopping (re-run the same command to resume)`.
- **Rate:** ≥ 0.2 s between KRX calls; ~13,000 calls in one afternoon hit no quota (~100
  trading days per minute per market).
- **data.go.kr:** whole tables, 10,000 rows per page; the gateway resets connections often, so
  each page is retried up to 8–10 times; `rights` writes pages to `raw/rights/.partial/` and
  resumes. Only the newest snapshot is kept; refreshed at most daily (dividends) / weekly (rights)
  unless `--force`.
- **Yahoo:** one request at a time, ≥ 2 s apart + 0–1 s jitter; after HTTP 429 waits 60, 180,
  600 s, stops at the 4th; stops at `--max-requests` (600). Every request is logged to
  `raw/yahoo/fetch_log.csv`.

## Build rules (`build.py`, `factors.py`, `lean_extras.py`)

| Output | Content |
|---|---|
| `lean/equity/krx/daily/{code}.zip` | `yyyyMMdd 00:00,o,h,l,c,v`, prices × 10,000, raw KRW |
| `lean/equity/krx/factor_files/{code}.csv` | `date,price_factor,split_factor,reference_price` |
| `lean/equity/krx/map_files/{code}.csv` | first trading date; `20501231` or the last trading date (delisting) |
| `lean/equity/krx/universe/yyyyMMdd.zip` | `code,market,close,volume,value,market_cap,shares` per trading day |
| `lean/equity/krx/securities.csv` | code → market, listing span, master fields |
| `lean/index/krx/daily/{kospi,kospi200}.zip` | index levels (not scaled) |
| `factor_events.csv` | every adjustment and dividend used (audit trail) |
| `ohlcv/`, `index/`, `dividends.csv`, `corporate_actions.csv` | CSVs for research |

- **Reproducible files:** every zip has one member with a fixed timestamp (1980-01-01), so the
  same content gives the same bytes; a file whose bytes wouldn't change is not rewritten (its
  modification time stays). `lean-install` (`sync_tree`) then copies only files that differ.
- **No-trade days:** KRX reports open/high/low 0 → replaced by the close; rows without a close
  are dropped.
- **Split factor** = product of KRX's own ratios. KRX reports the change `CMPPREVDD_PRC`
  against a base price; base = close − change. Base equals the previous close except on
  adjustment days (splits, reverse splits, bonus and rights issues, capital reductions,
  spin-offs), so `base / previous close` is the exchange's ratio. Rights issues are adjusted like
  splits (KRX's convention).
- **Price factor** = Π `(close − dividend) / close`, with the close of the last trading day
  before the ex-date. **Ex-date (T+2):** the trading day before the last trading day on or
  before the record date. A dividend whose ex-date is a KRX adjustment day is skipped (no double
  counting).
- **Dividend amounts:** only the reported amount (`stckGenrDvdnAmt`). The API's par value is
  *today's*, so `rate × par` is wrong before splits (유한양행 2000: reported 750 won; 15% × today's
  par 1,000 = 150). Records with only a rate (~13% since 2010) are skipped.
- **Factor file rows:** dated the last trading day before each event (reference price = that
  close), cumulative, plus a first row at the first trading date and `20501231,1,1,0`.
- **Map files:** first trading date, then `20501231`, or the last trading date if the security
  stopped trading before the newest date (LEAN's delisting signal).
- **Universe:** every security with a close that day, with KRX's market cap (`MKTCAP`), trading
  value and listed shares. LEAN reads the file for the *previous* trading day during selection.
- **Pruning:** codes without KRX data are removed from outputs; cross-check sources never feed
  outputs.
- **Corporate actions:** grouped by (company registration number, event type, `basDt`); `crno`
  → code via the dividend table (common share's ISIN), so some events have no code. Not used by
  factor files.

## LEAN install (`lean_install.py`)

Copies `lean/equity/krx` and `lean/index/krx` into a LEAN data folder (adds and replaces, never
deletes; removes a leftover `minute/`), and adds:
- `Equity-krx-[*]` to `market-hours/market-hours-database.json`: Asia/Seoul, pre-market
  08:30–09:00, market 09:00–15:30, post 15:40–18:00; holidays = LEAN's `Index-krx-[*]` list ∪
  every no-trade weekday in the data;
- `krx,[*],equity,,KRW,1,1,1` to `symbol-properties/symbol-properties-database.csv` (1-won step;
  real tick sizes come from the model).

`lean-package lean.zip` writes the same files in LEAN's layout (`data/equity/krx`, …) for
copying to another machine; `lean-install --config-only` then adds only the two config entries.

## Cross-checks

```bash
krx-lean --root ~/krx-data daily                     # aikstockdata: last 30 days
krx-lean --root ~/krx-data yahoo-daily 005930 069500 --start 2020-01-01   # needs .[crosscheck]
krx-lean --root ~/krx-data verify                    # → reports/verify_summary.csv, verify_mismatches.csv
```

Expected: 0 differences against aikstockdata (21,972 of 21,972 KOSPI stock-days identical on
2026-10-11). Yahoo differs before adjustment events (it back-adjusts) and occasionally in ETF
volume.

## Synthetic demo data (`demo.py`)

`krx-lean --root DIR demo` (or `klean data install --demo`) writes **made-up** raw files in the
exact formats of the real downloads — `raw/krx/{KOSPI,ETF}/…`, `raw/krx_index/KOSPI/…` (index
names 코스피 / 코스피 200, so the build writes `kospi` / `kospi200`), and a data.go.kr dividend
snapshot — then runs the normal `build`. Content: 29 stocks `D00010`…`D00280` (one preferred,
`D00015`), 3 ETFs `E000x0`, 2011-01-03 → 2026-09-30; a 5:1 split (D00020, 2018-05-04, KRX base
price = previous close / 5, so the split factor is exactly 0.2), a delisting (D00030,
2019-06-28), a listing (D00040, 2015-06-01), yearly cash dividends. Prices are seeded random
walks (one market factor pinned to ~4%/year, noise per stock netting to zero), on the tick grid;
the output is deterministic. klean passes LEAN's KRX holidays so the calendar matches LEAN's.

Marking: names "SYNTHETIC DEMO …", codes starting with `D`/`E` (no real KRX code does), and
`SYNTHETIC-DEMO-DATA.txt` in the root, `lean/equity/krx`, `lean/index/krx` and `ohlcv/`
(`lean-install` copies it into the workspace). klean reads the marker for its banners and the
`synthetic_demo_data` manifest flag, and refuses to mix demo and real data in one workspace.
`krx-lean demo` refuses a root that already has real downloads.

It's also the test data for anything that needs a whole data set without keys (unit tests use a
short range; CI can use the full one).

### `krx --sample`

KRX's public sample endpoint (`/svc/sample/apis`, key published in KRX's docs) returns the first
10 rows of a response: for prices a rotating handful of KOSPI stocks plus ETFs, for indices the
same 10 series every day, neither KOSPI nor KOSPI 200. It only smoke-tests the download code; no
strategy can run on its output.

## Why no minute data

Yahoo's KRX minute bars (the only free source tried) always stop at 14:59 (no 15:00–15:30 and no
closing auction), contain single-bar volume spikes holding 20–90% of a day's volume, have ~5.6%
of prices off the tick grid, and cover only ~28 days. Minute data stays out until a source that
includes the full session is available.

## Known limitations

- ~13% of cash dividends since 2010 have a rate but no amount and aren't in price factors.
- Rights issues are adjusted like splits; LEAN reports them as split events.
- ~33% of corporate-action events have no code (companies missing from the dividend table).
- Map files carry only first/last dates (no code changes or mergers).
- The data sources' terms apply: aikstockdata and Yahoo are non-commercial; data.go.kr 주식권리일정정보
  is 공공누리 type 2.
