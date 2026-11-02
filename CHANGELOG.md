# Changelog

## 0.0.1 — 2026-11 (first release, private)

First release as krx-lean (previously developed as qc-krx). Tested with LEAN commit
`80e7843f645673bcbeaab963049f76f20f6785e1` and .NET 10 on Ubuntu (native and WSL2).

- **Data pipeline** (`krx-lean`): KOSPI and ETF daily prices and the KOSPI index family from the
  KRX Open API (2010 onward), dividends and corporate-action dates from data.go.kr; LEAN daily,
  factor, map and universe files; KRX market hours and symbol properties; cross-checks against
  aikstockdata and Yahoo (optional `[crosscheck]` extra). `all` now includes dividends when
  `DATA_GO_KR_KEY` is set.
- **KRX models** in C# and Python (identical results): sell-side tax by settlement date,
  commission, tick sizes, daily universe, KOSPI / KOSPI 200 benchmark.
- **klean**: install LEAN and Python 3.11 (via uv), workspaces, project templates, backtests with
  run manifest and code snapshot, compare, logs, grid optimization, LEAN reports (HTML, PDF),
  local GUI. Under WSL2 the GUI opens the Windows browser through `wslview`.
- Strictly local: no Colab, Google Drive or Docker paths.
