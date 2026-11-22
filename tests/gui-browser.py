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
    expect(page.locator("h1").first).to_be_visible()
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

        check(page, errors, f"{scheme}-workspace", "#/", 0)
        expect(page.locator("#demobar")).to_be_visible()             # the demo workspace says so
        page.get_by_role("link", name="Cs", exact=True).first.click()
        expect(page.locator("h1")).to_contain_text("Cs")
        check(page, errors, f"{scheme}-project", "#/project/Cs", 0)

        # compare two runs from the project page
        boxes = page.locator("table input[type=checkbox]")
        boxes.nth(0).check()
        boxes.nth(1).check()
        page.get_by_role("button", name="Compare selected").click()
        expect(page.locator("h1")).to_contain_text("Comparison")
        expect(page.locator(".uplot")).to_have_count(1)
        print(f"ok  {scheme}-compare from the project page")

        # a run: equity + drawdown charts, legend follows the cursor, zoom, log scale
        page.goto(BASE + "#/project/Cs")
        page.locator("table a[href^='#/run/']").first.click()
        expect(page.locator(".uplot")).to_have_count(2)
        check(page, errors, f"{scheme}-run", "#" + page.url.split("#", 1)[1], 2)
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
            page.locator(".tabs a", has_text=tab).click()
        print(f"ok  {scheme}-run interactions")

        opt = next((WS / "Cs" / "optimizations").iterdir()).name
        check(page, errors, f"{scheme}-optimization", f"#/optimization/Cs/{opt}", 1)
        page.close()

    # Research: the workspace's JupyterLab inside the page, the project's notebook on the LEAN kernel
    page = browser.new_page(viewport={"width": 1400, "height": 950})
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "#/project/Py")
    page.get_by_role("link", name=re.compile("in Research")).click()
    expect(page.locator("iframe.lab")).to_be_visible(timeout=300_000)    # may install JupyterLab first
    lab = page.frame_locator("iframe.lab")
    expect(lab.locator(".jp-Notebook")).to_be_visible(timeout=120_000)
    lab.locator(".jp-CodeCell .cm-content").first.click()
    page.keyboard.press("Shift+Enter")
    expect(lab.locator(".jp-OutputArea-output").first).to_contain_text("securities", timeout=180_000)
    page.screenshot(path=str(SHOTS / "research.png"))
    if errors:
        raise SystemExit(f"research: browser errors: {errors}")
    print("ok  research: JupyterLab in the page, the notebook runs on LEAN")
    page.close()

    # a backtest started from the page finishes and shows up in the runs list
    page = browser.new_page(viewport={"width": 1300, "height": 900})
    page.goto(BASE + "#/project/HoldPy")
    runs_before = page.locator("table a[href^='#/run/']").count()
    page.locator("#bname").fill("from-gui")
    page.get_by_role("button", name="Start backtest").click()
    expect(page.locator("#jobstate")).to_contain_text("done", timeout=300_000)
    expect(page.locator("table a[href^='#/run/']")).to_have_count(runs_before + 1)
    page.get_by_role("link", name="open results").click()
    expect(page.locator(".uplot")).to_have_count(2)
    print("ok  backtest started from the page")
    browser.close()
JOBS.stop_all()
print(f"GUI BROWSER CHECK OK (screenshots in {SHOTS})")
