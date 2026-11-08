# 7. Testing and releases

## Unit tests

```bash
cd ~/krx-lean
python -m unittest discover -s tests            # pipeline (34, incl. the demo data through build and install)
python -m unittest discover -s tests/klean      # klean (36; some need dotnet on PATH)
```

They use small synthetic files; no keys, no network, no LEAN build needed.

## Verification record (on real data)

| Check | Result |
|---|---|
| aikstockdata vs KRX (`verify`, 2026-08-27 → 2026-10-07) | 21,972 of 21,972 KOSPI stock-days identical in all five fields |
| Yahoo daily vs KRX (12 codes, 2026-09) | 281 of 288 stock-days identical; 6 differ before an adjustment (Yahoo back-adjusts), 1 ETF volume |
| Full backfill 2010-01-04 → 2026-10 | KOSPI 4,371 days (~3.8M rows), ETF 4,372, KOSPI index family 4,371 days (53 indices) |
| Samsung 50:1 split | 2018-05-04 close 2,650,000 → 51,900, listed shares exactly 50×; base 53,000 / 2,650,000 = 0.02 |
| Base-price adjustments vs corporate actions (KOSPI) | 1,599 adjustments; 1,064 match a nearby corporate action; unmatched mostly preferred shares, delisted companies, funds |
| Factor files, whole market | on 22,207 event days, moves beyond ±30%: 634 raw → 7 adjusted (limit days and one fund paying out before delisting) |
| Holidays | all 248 no-trade weekdays in the data are in LEAN's KRX holiday list |
| Model self-checks (`CHECK` lines) | tax KOSPI 2018-06-01 0.30%, 2019-06-03 0.25%, 2025-01-02 0.15%, 2026-01-02 0.20%; tick 150,000 won 500 (2022) → 100 (2023); ETF 5 |
| Smoke test (`examples/KrxSmokeTest.cs`) | split factor 0.02 on 2018-05-04; dividends 354 won/quarter (Samsung); Woori Bank delisted 2019-02-12 and closed; account in KRW |
| C# = Python (top-market-cap) | identical statistics and equity curves (`klean compare`), identical reports |
| Optimization | best run of a 6-run grid identical to a plain backtest with those parameters |
| Strategy sanity (top 20 by market cap, 2011-01 → 2026-09) | CAGR 5.89% after fees; an independent pandas replication without fees: 6.36% |

## Verification record (synthetic demo data, no keys)

| Check | Result |
|---|---|
| Demo data through the real build | 32 securities on LEAN's KRX calendar, split factor exactly 0.2, a delisting map file, yearly dividends, both index files; deterministic |
| Templates on the demo data | buy-hold and top-market-cap run in Python and C#; top-market-cap C# = Python IDENTICAL; report, optimization and GUI carry the SYNTHETIC labels |
| Failure detection | a workspace without index data: `backtest FAILED` with the "no kospi200 index data" message, exit 1, manifest `ok: false`, in Python and C# |
| Research | starter notebook runs headless (`--execute`) and in JupyterLab in Chromium (all cells, both charts), for a Python and a C# project, in a fresh Python env (first-use install); a project `config.json` is ignored |

## Reproducibility

Every klean run records what produced it (`manifest.json`, `code/`, `config.json`). For results
you keep, also record the data state: the newest date in `raw/krx/KOSPI/`, the dividend
snapshot (`raw/dividends/<basDt>.csv.gz`), and `reports/verify_summary.csv` of that build. The
same raw files and the same krx-lean commit give the same LEAN data (file contents identical;
zip timestamps differ).

## Release checklist

1. Unit tests pass (both suites).
2. LEAN builds at `LEAN_COMMIT` from scratch (`klean install-lean` into an empty folder).
3. On real data: parity check ([4. KRX models](4-krx-models.md#parity-check-c--python)) prints
   IDENTICAL; a report and a small optimization complete; `klean research PROJECT --execute`
   runs the starter notebook (and the demo workspace's).
4. Users-track walkthrough on a clean Ubuntu 24.04 (native or WSL2), following only the docs:
   once without keys (the demo page: every template runs, everything says SYNTHETIC; a
   workspace without index data fails with the "no kospi200 index data" message), and once with
   keys.
5. Nothing that mustn't be published: `git ls-files` contains no data, keys, workspaces or
   third-party documents; run a secret scan.
6. `CHANGELOG.md` entry; version in `pyproject.toml`, `krx_lean/__init__.py`, `klean/__init__.py`;
   tag `vX.Y.Z`; release notes name the LEAN commit tested.

## Contributing

Keep changes to one concern; add a unit test for rule changes; for model changes, run the parity
check and paste the `klean compare` result; for data-rule changes, describe the effect on
`factor_events.csv` or `verify`.
