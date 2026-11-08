# 8. Roadmap

## klean, compared with the LEAN CLI

| LEAN CLI | klean |
|---|---|
| `init`, `create-project`, `delete-project`, `config`, `backtest`, `optimize`, `report`, `logs`, `gui`, `research` | ✅ (`optimize`: grid only; `research`: Python notebooks only) |
| `build` | `lean status` / `lean update` (no images) |
| `backtest --detach` | planned |
| `library add/remove` | planned: one shared copy of the KRX models instead of a copy per project |
| `backtest --debug` | planned (C# attach, debugpy) |
| `object-store` | later |
| `live …` | not in scope for now |
| `login`, `cloud …`, `data download`, `encrypt` | not applicable (QuantConnect services) |

KRX-specific additions: `doctor`, `data install/status`, run manifest and code snapshot,
`compare`; planned `check-models` (run the `CHECK` cases in both languages and compare).

## Data

- Thresholds for `verify` (fail a build on unexpected differences).
- Dividends with only a rate (~13%): amounts from another source (e.g. DART) or historical par.
- Map files: code changes and mergers.
- Universe flags (관리종목, 투자경고, 거래정지, sector): need another source.

## Models

- Verify the pre-2023 KOSDAQ/KONEX and January–October 2010 tick tables against KRX's rules.
- Slippage; fill model (±30% limits, auctions, VI); T+2 settlement; `KrxBrokerageModel`.
- Late opens in market hours (first trading day, 수능일).

## Scope and platforms

- macOS (Apple Silicon): check LEAN on .NET 10 arm64, pythonnet with `libpython3.11.dylib`,
  the report; then CI.
- CI on GitHub Actions: unit tests, LEAN build, backtests on the synthetic demo data
  (`klean data install --demo`; C# = Python parity).
- KOSDAQ / KONEX (code paths exist; needs KRX service approval and verification); NXT (no
  source yet); minute data (needs a source with the full session).
