// Live dashboard for one project: forward tests (paper trading on daily data). Step 3 of the
// dashboard plan fills this in; until then it explains what will be here.
import {app, backtestHash, esc, researchHash, setTitle} from "../util.js";

export async function pageLive(project) {
  setTitle(`Live · ${project}`);
  app.innerHTML = `<div class="dashhead">
      <a href="#/" class="back">‹ Workspace</a>
      <h1>${esc(project)}</h1>
      <span class="muted">Live</span>
      <span class="spacer"></span>
      <a class="button secondary" href="${researchHash(project)}">Research</a>
      <a class="button secondary" href="${backtestHash(project)}">Backtest</a>
    </div>
    <div class="cols">
      <div class="col-left"><div class="panel"><h2>Forward tests</h2>
        <p class="muted">Coming next: start a forward test from one of this project's backtests. After each
        <code>klean update data</code> the strategy runs on the new trading days with simulated fills
        (paper trading: no broker, no money).</p></div></div>
      <div class="col-right"><div class="panel"><p class="muted">The selected forward test will show here.</p></div></div>
    </div>`;
}
