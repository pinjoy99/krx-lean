// Live dashboard for one project: forward tests, i.e. paper trading on daily data. Left: start
// one (parameters from a backtest) and the list. Right: the selected test, its refresh history
// and its results (the same view as a backtest run).
import {api, app, backtestHash, esc, liveHash, researchHash, setTitle, signClass} from "../util.js";
import {renderRun} from "./run.js";

let shown = null;     // {project, data}

export async function pageLive(project, query) {
  setTitle(`Live · ${project}`);
  const left = document.getElementById("lv-left");
  if (!shown || shown.project !== project || !left || !document.body.contains(left)) await drawDashboard(project);
  await drawRight(new URLSearchParams(query || "").get("test") || shown.data.tests[0]?.id || "");
}

async function drawDashboard(project) {
  const p = await api("/api/live", {project});
  shown = {project, data: p};
  app.innerHTML = `<div class="dashhead">
      <a href="#/" class="back">‹ Workspace</a>
      <h1>${esc(p.name)} <span class="badge run">${esc(p.language)}</span></h1>
      <span class="muted">Live</span> <span class="badge paper">PAPER · forward tests</span>
      <span class="spacer"></span>
      <a class="button secondary" href="${researchHash(p.name)}">Research</a>
      <a class="button secondary" href="${backtestHash(p.name)}">Backtest</a>
    </div>
    <div class="cols">
      <div id="lv-left" class="col-left"></div>
      <div id="lv-right" class="col-right"></div>
    </div>`;
  drawLeft();
}

function stateBadge(t) {
  const cls = {running: "ok", stopped: "", failed: "no", "waiting for data": "run"}[t.state] ?? "";
  return `<span class="badge ${cls}">${esc(t.state)}</span>${t.backdated ? ' <span class="badge demo">backdated</span>' : ""}`;
}

function drawLeft() {
  const p = shown.data, el = document.getElementById("lv-left");
  el.innerHTML = `
    <details class="panel" id="newlive" ${p.tests.length ? "" : "open"}><summary><h2>Start a forward test</h2></summary>
      <p class="muted">Freezes ${esc(p.name)}'s code now. After each <code>klean update data</code> it runs on the new
        trading days with simulated fills (KRX fees, tax, slippage): paper trading, no broker, no money.</p>
      ${p.uses_period ? "" : `<div class="failbox">This project's code sets its own dates, so a forward test can't
        move them. In <code>main.py</code> replace <code>set_start_date</code> / <code>set_end_date</code> with
        <code>set_period(self, "2011-01-01")</code> (C#: <code>KrxModels.SetPeriod(this, "2011-01-01")</code>), after
        <code>klean update models ${esc(p.name)}</code> if its krx_models is older.</div>`}
      <label class="field">Parameters from
        <select id="lvrun"><option value="">the code's defaults</option>
          ${p.runs.map(r => `<option value="${esc(r.ref)}">${esc(r.name)}${Object.keys(r.parameters).length ? " · " + esc(Object.entries(r.parameters).map(([k, v]) => k + "=" + v).join(", ")) : ""}</option>`).join("")}
        </select></label>
      <div class="grid2">
        <label class="field">Name (optional)<input type="text" id="lvname" placeholder="e.g. 30 holdings"></label>
        <label class="field">Start date (empty: the next trading day)<input type="text" id="lvstart" placeholder="after ${esc(p.data_last_date)}"></label>
      </div>
      <p class="muted small2">A date on or before ${esc(p.data_last_date)} (the latest data) makes a <b>backdated</b> test: the code may
        have been written knowing those days, so it isn't a true forward test.</p>
      <div class="row"><button id="lvgo" ${p.uses_period ? "" : "disabled"}>Start forward test</button><span id="lvstate" class="muted"></span></div>
    </details>
    <div class="panel"><h2>Forward tests (${p.tests.length})</h2>
      ${p.tests.length ? `<table class="runs"><tr><th>Forward test</th><th>From</th><th class="num">Net profit</th></tr>
        ${p.tests.map(t => `<tr data-test="${esc(t.id)}"><td><a href="${liveHash(p.name, t.id)}">${esc(t.name)}</a><div>${stateBadge(t)}</div></td>
          <td>${esc(t.start_date)}<div class="muted small2">to ${esc(t.last_refresh?.data_last_date || "—")}</div></td>
          <td class="num ${signClass(t.stats["Net Profit"])}">${esc(t.stats["Net Profit"] || "—")}</td></tr>`).join("")}</table>`
        : '<p class="muted">None yet.</p>'}
    </div>`;
  const $ = id => document.getElementById(id);
  $("lvgo").onclick = async () => {
    const btn = $("lvgo"), state = $("lvstate");
    btn.disabled = true; state.textContent = "starting…";
    try {
      const job = await api("/api/live-start", {}, {project: p.name, run: $("lvrun").value, name: $("lvname").value.trim(),
                                                    start: $("lvstart").value.trim()});
      await waitFor(job, state);
      shown.data = await api("/api/live", {project: p.name});
      drawLeft();
      location.hash = liveHash(p.name, job.test);
    } catch (e) { state.innerHTML = `<span class="err">${esc(e.message)}</span>`; btn.disabled = false; }
  };
}

// Poll a forward-test job until it ends; shows progress in `state`.
async function waitFor(job, state) {
  for (;;) {
    const j = await api("/api/job", {id: job.id});
    if (j.status !== "running") {
      if (j.status === "failed") throw new Error(j.error.split("\n")[0]);
      return j;
    }
    state.innerHTML = `<span class="badge run">running</span> ${Math.round(Date.now() / 1000 - j.started)} s`;
    await new Promise(r => setTimeout(r, 1500));
  }
}

async function drawRight(id) {
  const el = document.getElementById("lv-right"), p = shown.data;
  document.querySelectorAll("#lv-left tr[data-test]").forEach(tr => tr.classList.toggle("sel", tr.dataset.test === id));
  if (!id) {
    el.innerHTML = `<div class="panel"><h2>No forward tests yet</h2><p class="muted">Start one on the left. It runs
      the code as it is now on days that come after today's data, so its results are out of sample.</p></div>`;
    return;
  }
  el.innerHTML = '<p class="muted">Loading…</p>';
  let t;
  try { t = await api("/api/live-test", {project: p.name, id}); }
  catch (e) { el.innerHTML = `<div class="panel"><div class="err">${esc(e.message)}</div></div>`; return; }
  const params = Object.entries(t.parameters).map(([k, v]) => `${esc(k)}=${esc(v)}`).join(", ") || "the code's defaults";
  el.innerHTML = `<div class="panel">
      <div class="row"><h2 class="runtitle" style="margin:0">${esc(t.name)}</h2> ${stateBadge(t)}
        <span class="spacer" style="flex:1"></span>
        ${t.status === "running" ? '<button class="secondary" id="lvrefresh">Run to the latest data</button><button class="secondary" id="lvstop">Stop</button>' : ""}</div>
      <p class="muted">From <b>${esc(t.start_date)}</b> with ${params}${t.source_run ? ` (from ${esc(t.source_run)})` : ""}.
        Code frozen ${esc(t.created_utc.slice(0, 10))}, when the data ended ${esc(t.data_last_date_at_start)}.
        ${t.state === "waiting for data" ? `Waiting for data after ${esc(t.start_date)}: <code>klean update data</code> runs it.` : ""}</p>
      <span id="lvmsg" class="muted"></span>
      ${t.history.length ? `<details><summary class="muted">Refreshes (${t.history.length})</summary><table class="runs">
        <tr><th>When (UTC)</th><th>Data to</th><th class="num">End equity</th><th></th></tr>
        ${t.history.map(h => `<tr><td>${esc(h.at.replace("T", " ").replace("Z", ""))}</td><td>${esc(h.data_last_date)}</td>
          <td class="num">${esc(h.end_equity ?? "")}</td><td>${h.ok ? "" : `<span class="err">${esc(h.error)}</span>`}</td></tr>`).join("")}</table></details>` : ""}
    </div>
    <div id="lvrun-view">${t.ref ? "" : '<p class="muted">No results yet.</p>'}</div>`;
  if (t.ref) await renderRun(document.getElementById("lvrun-view"), t.ref);
  const refresh = document.getElementById("lvrefresh");
  if (refresh) {
    refresh.onclick = async () => {
      refresh.disabled = true;
      try {
        const j = await waitFor(await api("/api/live-refresh", {}, {project: p.name, id}), document.getElementById("lvmsg"));
        shown.data = await api("/api/live", {project: p.name}); drawLeft();
        await drawRight(id);
        if (j.note) document.getElementById("lvmsg").textContent = j.note;
      } catch (e) { document.getElementById("lvmsg").innerHTML = `<span class="err">${esc(e.message)}</span>`; refresh.disabled = false; }
    };
    document.getElementById("lvstop").onclick = async () => {
      if (!confirm(`Stop the forward test ${t.name}? It won't run on new days any more; its results stay.`)) return;
      await api("/api/live-stop", {}, {project: p.name, id});
      shown.data = await api("/api/live", {project: p.name}); drawLeft();
      await drawRight(id);
    };
  }
}
