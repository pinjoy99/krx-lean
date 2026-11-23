#!/usr/bin/env bash
# End-to-end check on the SYNTHETIC demo data: no API keys, no real market data.
# Builds LEAN and the Python 3.11 environment if they aren't there, then runs every klean
# feature and checks the results. Used by CI (.github/workflows/ci.yml) and runnable by hand:
#
#   tests/e2e-demo.sh                      # everything in a temporary folder (~15 min the first time)
#   LEAN_DIR=~/Lean PY_DIR=~/.klean/py311 tests/e2e-demo.sh     # reuse an existing setup (~5 min)
#
# Needs `klean` (pip install -e .), dotnet 10 and uv on the PATH.
set -euo pipefail

WORK=${E2E_DIR:-$(mktemp -d)}
LEAN_DIR=${LEAN_DIR:-$WORK/Lean}
PY_DIR=${PY_DIR:-$WORK/py311}
WS=$WORK/ws-$$
step() { printf '\n=== %s\n' "$*"; }
fail() { echo "E2E FAILED: $*" >&2; exit 1; }

step "LEAN and Python 3.11"
[ -f "$LEAN_DIR/Launcher/bin/Release/QuantConnect.Lean.Launcher.dll" ] || klean install lean --dir "$LEAN_DIR" >"$WORK/lean-build.log" 2>&1 \
  || { tail -40 "$WORK/lean-build.log"; fail "LEAN build"; }
[ -x "$PY_DIR/bin/python" ] || klean install python --dir "$PY_DIR"

step "workspace with synthetic demo data"
klean init "$WS" --lean "$LEAN_DIR" --python-venv "$PY_DIR"
cd "$WS"
klean install data --demo
klean doctor || fail "doctor reports a problem"
klean status data | grep -q "SYNTHETIC DEMO DATA" || fail "data status doesn't say the data is synthetic"
klean status all | grep -q "no projects" || fail "status all"
klean data status >/dev/null || fail 'the 0.0.9 name "klean data status" no longer works'

step "backtests: C# and Python must be identical"
klean create-project Cs --language csharp --template top-market-cap
klean create-project Py --template top-market-cap
klean backtest Cs
klean backtest Py
klean compare Py Cs | tee compare.txt
grep -qx "IDENTICAL" compare.txt || fail "the C# and Python results differ"
grep -q '"synthetic_demo_data": true' Cs/backtests/*/manifest.json || fail "manifest lacks the demo flag"
ls Py/backtests/*/code/main.py >/dev/null || fail "no code snapshot"

step "slippage: costs money, and stays identical in both languages"
klean backtest Cs --parameter slippage_ticks 1 --backtest-name slip
klean backtest Py --parameter slippage_ticks 1 --backtest-name slip
SLIP_CS=$(basename "$(ls -d Cs/backtests/*_slip)"); SLIP_PY=$(basename "$(ls -d Py/backtests/*_slip)")
klean compare "Py/$SLIP_PY" "Cs/$SLIP_CS" | tail -1 | grep -qx "IDENTICAL" || fail "slippage differs between C# and Python"
"$PY_DIR/bin/python" - <<'EOF' || fail "one tick of slippage didn't lower the end equity"
import glob, json
def equity(pattern):
    runs = sorted(glob.glob(pattern))
    return float(json.load(open(runs[0]))["statistics"]["End Equity"])
plain = equity("Cs/backtests/*[0-9]/*-summary.json")
slipped = equity("Cs/backtests/*_slip/*-summary.json")
assert slipped < plain, (plain, slipped)
print(f"end equity {plain:,.0f} -> {slipped:,.0f} with 1 tick of slippage")
EOF

step "models check and update"
klean status models | grep -q "current" || fail "models status"
echo "# edited" >> Py/krx_models.py
klean doctor | grep -q "note: Py differ" || fail "doctor doesn't note the edited models"
klean update models Py | grep -q "updated" || fail "models update"
[ -f Py/krx_models.py.bak ] || fail "no backup of the edited models"

step "KOSDAQ: its own taxes and tick sizes, identical in both languages"
klean backtest Cs --parameter market KOSDAQ --parameter holdings 3 --parameter slippage_ticks 1 --backtest-name kosdaq
klean backtest Py --parameter market KOSDAQ --parameter holdings 3 --parameter slippage_ticks 1 --backtest-name kosdaq
KQ_CS=$(basename "$(ls -d Cs/backtests/*_kosdaq)"); KQ_PY=$(basename "$(ls -d Py/backtests/*_kosdaq)")
klean compare "Py/$KQ_PY" "Cs/$KQ_CS" | tail -1 | grep -qx "IDENTICAL" || fail "KOSDAQ run differs between C# and Python"
grep -q '"Total Orders": "[1-9]' "Cs/backtests/$KQ_CS"/*-summary.json || fail "the KOSDAQ run placed no orders"

step "buy-hold template, both languages"
klean create-project HoldPy
klean create-project HoldCs --language csharp
klean backtest HoldPy
klean backtest HoldCs
klean compare HoldPy HoldCs | tail -1 | grep -qx "IDENTICAL" || fail "buy-hold differs between C# and Python"

step "a strategy that raises must be reported as failed"
klean create-project Broken --template empty
"$PY_DIR/bin/python" - <<'EOF'     # (not sed -i: GNU and BSD/macOS sed differ)
import pathlib
p = pathlib.Path("Broken/main.py")
p.write_text(p.read_text().replace('self.set_benchmark(krx_benchmark("kospi200"))',
                                   'raise ValueError("e2e: deliberate failure")'))
EOF
grep -q "deliberate failure" Broken/main.py || fail "couldn't break the template"
if klean backtest Broken >broken.txt 2>&1; then fail "a failing strategy exited 0"; fi
grep -q "backtest FAILED" broken.txt || fail "no 'backtest FAILED' message"
grep -q "deliberate failure" broken.txt || fail "the strategy's error isn't shown"

step "time limit"
if klean backtest Py --timeout 2 >timeout.txt 2>&1; then fail "--timeout 2 didn't stop the run"; fi
grep -q "timed out after 2 s" timeout.txt || fail "no timeout message"

step "live paper trading (klean's LEAN plugin): buy-hold, same fill as a backtest of the same days"
klean live deploy HoldPy --name e2e --start 2026-09-23 | tee live.txt
grep -q "BACKDATED" live.txt || fail "a backdated deployment isn't labeled so"
python - <<'EOF2' || fail "live paper trading"
import glob, json
book = json.load(open(glob.glob("HoldPy/live/*_e2e/ledger.json")[0]))
fills = book["fills"]
assert len(fills) == 1 and fills[0]["session"] == "2026-09-28", fills          # ordered on 09-23, filled at the next open
assert book["open_orders"] == [] and book["last_session"] == "2026-09-30", book
json.dump(fills[0], open("live-fill.json", "w"))
print("live fill", fills[0])
EOF2
klean backtest HoldPy --parameter start_date 2026-09-23 --parameter end_date 2026-09-30 --backtest-name livecheck >/dev/null
python - <<'EOF2' || fail "the live fill differs from the backtest's"
import glob, json
live_fill = json.load(open("live-fill.json"))
run = sorted(glob.glob("HoldPy/backtests/*_livecheck"))[-1]
fills = [e for e in json.load(open(glob.glob(run + "/*-order-events.json")[0])) if e["status"] == "filled"]
assert len(fills) == 1, fills
assert (fills[0]["fillQuantity"], fills[0]["fillPrice"]) == (live_fill["quantity"], live_fill["price"]), (fills[0], live_fill)
print("backtest fill", fills[0]["fillQuantity"], fills[0]["fillPrice"], "= live")
EOF2
klean live status HoldPy | grep -q "running (backdated)" || fail "live status"
klean live run HoldPy | grep -q "nothing new" || fail "a second run should find no new days"

step "live paper trading: the top-market-cap universe, identical in C# and Python"
klean live deploy Py --name uni --start 2026-09-28 --parameter holdings 5 >/dev/null
klean live deploy Cs --name uni --start 2026-09-28 --parameter holdings 5 >/dev/null
python - <<'EOF2' || fail "the universe strategy in live mode"
import glob, json
books = {lang: json.load(open(glob.glob(f"{lang}/live/*_uni/ledger.json")[0])) for lang in ("Py", "Cs")}
fills = {lang: [(f["session"], f["symbol"], f["quantity"], f["price"], f["commission"], f["tax"]) for f in b["fills"]]
         for lang, b in books.items()}
assert len({f[1] for f in fills["Py"] if f[0] == "2026-09-29"}) == 5, fills["Py"]       # 5 stocks bought at the next open
assert fills["Py"] == fills["Cs"], fills
assert books["Py"]["equity"] == books["Cs"]["equity"], (books["Py"]["equity"], books["Cs"]["equity"])
print("universe live: identical in C# and Python,", len(fills["Py"]), "fills")
EOF2
klean live stop Py "$(basename "$(ls -d Py/live/*_uni)")" | grep -q "stopped" || fail "live stop"

step "optimize"
klean optimize Cs --parameter holdings 10 20 10 --max-concurrent-backtests 2 --name e2e
grep -q '"best": "00' Cs/optimizations/*_e2e/optimization.json || fail "the optimization has no best run"

step "report"
klean report Cs
RUN=$(ls -d Cs/backtests/*/ | tail -1)
[ -s "$RUN/report.html" ] || fail "no report.html"
grep -q "SYNTHETIC DEMO DATA" "$RUN/report.html" || fail "the report doesn't say the data is synthetic"

step "research notebook"
klean research Py --execute
"$PY_DIR/bin/python" - <<'EOF' || fail "the executed notebook lacks its outputs"
import json
nb = json.load(open("Py/research.executed.ipynb"))
outputs = [o for c in nb["cells"] if c["cell_type"] == "code" for o in c["outputs"]]
errors = [o for o in outputs if o["output_type"] == "error"]
charts = [o for o in outputs if "image/png" in o.get("data", {})]
assert not errors and len(charts) == 2, (len(errors), len(charts))
EOF

step "E2E OK ($WS)"
