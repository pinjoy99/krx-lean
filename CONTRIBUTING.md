# Contributing to krx-lean

Thanks for helping. Bug reports, questions and fixes are all welcome.

## Reporting a problem

Open an [issue](https://github.com/pinjoy99/krx-lean/issues/new/choose) and include:

- what you ran and what happened (the last lines `klean` printed; for a failed backtest, the end
  of `klean logs PROJECT --console`);
- the output of `klean doctor` and `klean --version`;
- your system (Ubuntu version, WSL2 or native).

**Never paste API keys.** krx-lean hides keys in its own messages, but check anything you copy
from a terminal or a log for `KRX_API_KEY`, `DATA_GO_KR_KEY` or `serviceKey=` values first.
Don't attach market data either: it can't be redistributed. If a problem needs data to
reproduce, try it on the synthetic demo data (`klean data install --demo`) or name the stock
code and date.

Security problems: see [SECURITY.md](SECURITY.md), not a public issue.

## Changing code or docs

1. Fork, create a branch, and install from your clone: `pip install -e . pyflakes`.
2. Make the change. Keep it to one concern; match the style of the code around it.
3. Run the checks:

   ```bash
   python -m pyflakes krx_lean klean tests
   python -m unittest discover -s tests
   python -m unittest discover -s tests/klean
   LEAN_DIR=~/Lean PY_DIR=~/.klean/py311 tests/e2e-demo.sh    # needs LEAN built; ~4 min
   ```

   CI runs the same on every pull request, on synthetic demo data, without keys.
4. Open a pull request that says what changes and how you checked it.

What reviewers look for:

- **Data rules** (`krx_lean/`): a unit test for the rule, and what it changes in
  `factor_events.csv` or `krx-lean verify`.
- **KRX models** (`examples/KrxModels.cs` and `examples/python/krx_models.py`): the same change
  in both files, the source of any rate or table (add it to
  [docs/dev/4-krx-models.md](docs/dev/4-krx-models.md)), and `klean compare` printing
  `IDENTICAL` for the C# and Python runs.
- **klean**: standard library only; nothing that needs Docker, an account or a cloud service.
- **Docs**: commands in the docs must run as written.

More background: [docs/dev/](docs/dev/), especially
[7. Testing and releases](docs/dev/7-testing-and-release.md).

## Scope

krx-lean covers KOSPI and KOSDAQ stocks and ETFs with daily data, for backtesting and research on your own
machine. Live trading, other markets and intraday data are outside the current scope; open an
issue to discuss before starting on them.

By contributing you agree that your contribution is licensed under the
[Apache-2.0 license](LICENSE).
