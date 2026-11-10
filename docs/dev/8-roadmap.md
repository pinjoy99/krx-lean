# 8. Roadmap

## klean, compared with the LEAN CLI

| LEAN CLI | klean |
|---|---|
| `init`, `create-project`, `delete-project`, `config`, `backtest`, `optimize`, `report`, `logs`, `gui`, `research` | ✅ (`optimize`: grid only; `research`: Python notebooks only) |
| `build` | `lean status` / `lean update` (no images) |
| `backtest --detach` | planned |
| `library add/remove` | partly: `klean models status/update` keeps per-project copies current; a shared library later |
| `backtest --debug` | planned (C# attach, debugpy) |
| `object-store` | later |
| `live …` | not in scope for now |
| `login`, `cloud …`, `data download`, `encrypt` | not applicable (QuantConnect services) |

KRX-specific additions: `doctor`, `data install/status`, synthetic demo data
(`data install --demo`), run manifest and code snapshot, failure detection from LEAN's run
status, `compare`; planned `check-models` (run the `CHECK` cases in both languages and compare).
`research`: C# notebooks (.NET Interactive) later, if wanted.

## Data

- Thresholds for `verify` (fail a build on unexpected differences).
- Dividends with only a rate (~13%): amounts from another source (e.g. DART) or historical par.
- Map files: code changes and mergers.
- Universe flags (관리종목, 투자경고, 거래정지, sector): need another source.

## Models

- Verify the pre-2023 KOSDAQ/KONEX and January–October 2010 tick tables against KRX's rules.
- Slippage: fixed ticks per share done (`KrxSlippageModel`, off by default); next a
  volume-share / market-impact model, and whether 1 tick should become the default.
- Fill model (±30% limits, auctions, VI); T+2 settlement; `KrxBrokerageModel`.
- Late opens in market hours (first trading day, 수능일).

## Scope and platforms

- macOS (Apple Silicon): check LEAN on .NET 10 arm64, pythonnet with `libpython3.11.dylib`,
  the report; then CI.
- CI: done for Ubuntu (unit suites, LEAN build, end-to-end on the demo data). Next: a scheduled
  job trying the newest LEAN commit; a release workflow creating tags.
- KOSDAQ / KONEX (code paths exist; needs KRX service approval and verification); NXT (no
  source yet); minute data (needs a source with the full session).
