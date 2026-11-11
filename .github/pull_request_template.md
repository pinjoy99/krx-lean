## What changes

## How it was checked

- [ ] `python -m pyflakes krx_lean klean tests` and both unit suites pass
- [ ] `tests/e2e-demo.sh` passes (or CI does)
- [ ] KRX models changed: both `KrxModels.cs` and `krx_models.py`, and `klean compare` prints IDENTICAL
- [ ] Docs updated where behaviour changed
- [ ] No API keys or market data in the diff
