# Security policy

## Reporting a vulnerability

Please report security problems privately: use **Report a vulnerability** on the repository's
[Security tab](https://github.com/pinjoy99/krx-lean/security/advisories/new). Don't open a
public issue for them. You should get a reply within a week.

Useful reports include: API keys ending up in output, logs or files; `klean gui` or
`klean research` being reachable or usable by something other than the local user; files
written outside a workspace or data folder; code execution from data files; any way klean could
send an order to a KIS real-trading server or a real-money account (klean is paper only).

## What to know when using krx-lean

- **API keys** (KRX Open API, data.go.kr, and the optional KIS 모의투자 keys `KIS_PAPER_…`) are
  read from environment variables or `~/.config/krx-lean.env`. Keep that file readable only by
  you (`chmod 600`); never commit keys or paste them into issues. If a key was exposed, reissue
  it on the provider's site.
- **KIS-PAPER login tokens** are cached in `~/.klean/kis-token-paper-*.json` (readable only by
  you; valid about a day). Delete them if the machine is shared.
- **Paper only.** klean connects only to KIS's 모의투자 server and has no real-money mode. Use
  the 모의투자 account's keys; don't put a real account's keys in the file.
- **`klean gui` and `klean research`** listen on 127.0.0.1 only and require a random token that
  is part of the URL they print. Anyone with that URL and access to your machine can use them,
  so don't share it, and stop them (Ctrl+C) when you're done.
- **Strategies and notebooks are code.** A backtest runs the project's code with your user's
  permissions, and installs the project's `requirements.txt`. Only run projects you trust.
- **Supported versions:** the latest release on `main`.
