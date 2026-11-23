"""Browser check of `klean gui` on a workspace with runs (the one tests/e2e-demo.sh leaves).

    python tests/gui-browser.py WORKSPACE [SCREENSHOT_DIR]

Needs `pip install playwright` and a Chromium for it (`python -m playwright install chromium`,
or KLEAN_CHROMIUM=/path/to/chromium). Opens every page in light and dark mode and fails on a
browser console error, a missing chart, or an interaction that doesn't work: chart zoom and
legend, log scale, compare from the project page, and a backtest started from the page.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

# the repository, not tests/klean/ (this script's folder comes first on sys.path)
sys.path[0] = str(Path(__file__).resolve().parents[1])

WS = Path(sys.argv[1]).resolve()
SHOTS = Path(sys.argv[2] if len(sys.argv) > 2 else WS / "gui-shots")
SHOTS.mkdir(parents=True, exist_ok=True)


def start_gui() -> str:
    """`klean gui` in a thread of this process, on a free port with a known token: a startup
    error shows up here with its traceback."""
    import socket
    import threading
    import traceback
    import urllib.request

    from klean import gui
    from klean.workspace import Workspace

    global JOBS
    JOBS = gui.Jobs()                  # its JupyterLab is stopped at the end, as `klean gui` does

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    token = "browser-check"
    failed: list[str] = []

    def run():
        try:
            server = gui.LocalServer(("127.0.0.1", port), gui.make_handler(Workspace.load(WS), token, JOBS))
            server.serve_forever()
        except BaseException:          # noqa: BLE001 - reported below
            failed.append(traceback.format_exc())

    threading.Thread(target=run, daemon=True).start()
    url = f"http://127.0.0.1:{port}/?token={token}"
    deadline, last_error = time.time() + 30, None
    while time.time() < deadline and not failed:
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return url
        except OSError as e:
            last_error = e
            time.sleep(0.3)
    print(f"last error: {last_error!r}", file=sys.stderr)
    if not failed:                    # hanging somewhere: show where every thread is
        import faulthandler
        faulthandler.dump_traceback(all_threads=True)
    raise SystemExit("klean gui didn't start:\n" + ("".join(failed) or f"no answer from {url} in 30 s"))


def check(page: Page, errors: list[str], name: str, hash_: str, charts: int) -> None:
    page.goto(BASE + hash_)
    try:
        expect(page.locator("h1").first).to_be_visible(timeout=20_000)
    except AssertionError:
        raise SystemExit(f"{name}: page didn't render; browser errors: {errors}") from None
    expect(page.locator(".uplot")).to_have_count(charts)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)
    if errors:
        raise SystemExit(f"{name}: browser errors: {errors}")
    print(f"ok  {name}")


JOBS = None
BASE = start_gui()
with sync_playwright() as pw:
    exe = os.environ.get("KLEAN_CHROMIUM")
    browser = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
    for scheme in ("light", "dark"):
        page = browser.new_page(viewport={"width": 1300, "height": 900}, color_scheme=scheme)
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # Workspace dashboard: projects on the left, data / setup / settings on the right
        check(page, errors, f"{scheme}-workspace", "#/", 0)
        expect(page.locator("#demobar")).to_be_visible()             # the demo workspace says so
        expect(page.locator(".col-right h2", has_text="Setup check")).to_be_visible()

        # Backtest dashboard from the project's "last backtest" cell: the latest run on the right
        row = page.locator("table.runs tr", has=page.locator("a.projlink", has_text=re.compile("^Cs$")))
        row.locator("a[href*='?run=']").click()
        expect(page.locator(".dashhead h1")).to_contain_text("Cs")
        expect(page.locator("#bt-right .uplot")).to_have_count(2)
        expect(page.locator("#bt-left tr.sel")).to_have_count(1)
        check(page, errors, f"{scheme}-backtest", "#" + page.url.split("#", 1)[1], 2)

        # choosing another run redraws only the right column (the form keeps what was typed)
        page.locator("#bname").fill("kept")
        first_title = page.locator("#bt-right .runtitle").inner_text()
        page.locator("#bt-left tr[data-ref] a").nth(1).click()
        expect(page.locator("#bt-right .runtitle")).not_to_have_text(first_title)
        expect(page.locator("#bname")).to_have_value("kept")
        expect(page.locator("#bt-left tr.sel")).to_have_count(1)

        # the run's charts: legend follows the cursor, zoom, log scale; its tabs
        eq = page.locator("#eq .u-over")
        legend_date = page.locator("#eq .u-legend .u-series").first.locator(".u-value")
        last = legend_date.inner_text()
        box = eq.bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.25, box["y"] + box["height"] / 2)
        expect(legend_date).not_to_have_text(last)                    # the cursor's date
        x_range = "() => { const x = document.getElementById('eq').uplot.scales.x; return x.max - x.min; }"
        before = page.evaluate(x_range)
        page.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + 20)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] * 0.45, box["y"] + 20, steps=5)
        page.mouse.up()
        page.wait_for_function(f"({x_range})() < {before} * 0.5")       # zoomed in
        page.locator("#eq .chartopt input").check()                   # log scale redraws
        expect(page.locator("#eq .uplot")).to_have_count(1)
        for tab in ("Orders", "Log", "Code", "Run record", "Statistics"):
            page.locator("#bt-right .tabs a", has_text=tab).click()
        print(f"ok  {scheme}-run interactions")

        # compare: tick two runs, the comparison takes the right column
        boxes = page.locator("#bt-left input[type=checkbox]")
        boxes.nth(0).check()
        boxes.nth(1).check()
        page.get_by_role("button", name="Compare selected").click()
        expect(page.locator("#bt-right .runtitle")).to_contain_text("Comparison of 2 runs")
        expect(page.locator("#bt-right .uplot")).to_have_count(1)
        print(f"ok  {scheme}-compare in the right column")

        # an optimization from the left column
        page.locator("#bt-left tr[data-opt] a").first.click()
        expect(page.locator("#bt-right .runtitle")).to_contain_text("Optimization")
        expect(page.locator("#bt-right .uplot")).to_have_count(1)
        page.screenshot(path=str(SHOTS / f"{scheme}-optimization.png"), full_page=True)
        print(f"ok  {scheme}-optimization in the right column")

        # Live dashboard is reachable from the title bar
        page.locator(".dashhead a", has_text="Live").click()
        expect(page.locator(".dashhead")).to_contain_text("Live")
        if errors:
            raise SystemExit(f"{scheme}: browser errors: {errors}")
        page.close()

    # old addresses (bookmarks, earlier versions) lead to the new dashboards
    page = browser.new_page(viewport={"width": 1300, "height": 900})
    some_run = sorted((WS / "Cs" / "backtests").iterdir())[0].name
    page.goto(BASE + f"#/run/Cs/{some_run}")
    expect(page.locator("#bt-right .runtitle")).to_contain_text(some_run)
    page.goto(BASE + "#/project/Cs")
    expect(page.locator("#bt-left")).to_be_visible()
    print("ok  old addresses")
    page.close()

    # Research: the workspace's JupyterLab inside the page, the project's notebook on the LEAN kernel
    page = browser.new_page(viewport={"width": 1400, "height": 950})
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "#/")
    page.locator("a.projlink", has_text=re.compile("^Py$")).click()
    expect(page.locator(".dashhead a.button", has_text="Backtest")).to_be_visible()
    expect(page.locator("iframe.lab")).to_be_visible(timeout=300_000)    # may install JupyterLab first
    lab = page.frame_locator("iframe.lab")
    expect(lab.locator(".jp-Notebook")).to_be_visible(timeout=120_000)
    # wait until the kernel (with LEAN loaded) is idle: a keypress sent earlier can be lost
    expect(lab.get_by_text(re.compile(r"\| Idle"))).to_be_visible(timeout=180_000)
    output = lab.locator(".jp-OutputArea-output").first
    for attempt in range(3):
        lab.locator(".jp-CodeCell .cm-content").first.click()
        if attempt == 0:
            page.keyboard.press("Shift+Enter")
        else:                          # the toolbar's Run button, if the keypress didn't reach the cell
            lab.locator(".jp-NotebookPanel-toolbar [data-command='notebook:run-cell-and-select-next']").click()
        try:
            expect(output).to_contain_text("securities", timeout=90_000)
            break
        except AssertionError:
            if attempt == 2:
                raise
            print(f"research: no output yet (attempt {attempt + 1}), running the cell again")
    page.screenshot(path=str(SHOTS / "research.png"))
    if errors:
        raise SystemExit(f"research: browser errors: {errors}")
    print("ok  research: JupyterLab in the page, the notebook runs on LEAN")
    page.close()

    # a backtest started from the page finishes and shows up in the runs list
    page = browser.new_page(viewport={"width": 1300, "height": 900})
    page.goto(BASE + "#/backtest/HoldPy")
    expect(page.locator("#bt-left")).to_be_visible()
    runs_before = page.locator("#bt-left tr[data-ref]").count()
    page.locator("#bname").fill("from-gui")
    page.get_by_role("button", name="Start backtest").click()
    expect(page.locator("#jobstate")).to_contain_text("done", timeout=300_000)
    expect(page.locator("#bt-left tr[data-ref]")).to_have_count(runs_before + 1)
    expect(page.locator("#bt-right .runtitle")).to_contain_text("from-gui")      # the new run is shown
    expect(page.locator("#bt-right .uplot")).to_have_count(2)
    print("ok  backtest started from the page")

    # Live: deploy from the page; it trades the days and shows its account
    page.goto(BASE + "#/live/HoldPy")
    expect(page.locator("#lv-left")).to_be_visible()
    if page.locator("#newlive").get_attribute("open") is None:     # folded once deployments exist
        page.locator("#newlive summary").click()
    page.locator("#lvname").fill("from-gui")
    page.locator("#lvstart").fill("2026-09-28")
    page.get_by_role("button", name="Deploy").click()
    expect(page.locator("#lv-left tr.sel")).to_contain_text("from-gui", timeout=600_000)
    expect(page.locator("#lv-left tr.sel")).to_contain_text("backdated")
    expect(page.locator("#lv-right .tile", has_text="Trading days")).to_contain_text("3")
    expect(page.locator("#lveq .uplot")).to_have_count(1)
    page.locator("#lv-right .tabs a", has_text="Fills").click()
    expect(page.locator("#lv-right [data-p=fills] table tr")).to_have_count(2)       # header + the buy
    page.locator("#lv-right .tabs a", has_text="Daily runs").click()
    page.locator("#lv-right a[data-console]").first.click()
    expect(page.locator("#lvconsole")).to_contain_text("KrxPaperBrokerage")
    page.screenshot(path=str(SHOTS / "live.png"), full_page=True)
    page.goto(BASE + "#/")
    row = page.locator("table.runs tr", has=page.locator("a.projlink", has_text=re.compile("^HoldPy$")))
    expect(row.locator("a[href*='#/live/']")).to_contain_text("from-gui")      # Workspace: last live run
    print("ok  paper deployment from the Live page")
    browser.close()
JOBS.stop_all()
print(f"GUI BROWSER CHECK OK (screenshots in {SHOTS})")
