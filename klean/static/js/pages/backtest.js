// Backtest dashboard for one project. Left: new backtest / optimization forms, the runs list
// (tick two or more to compare) and the optimizations. Right: the selected run (default: the
// latest), an optimization, or a comparison. Moving between runs only redraws the right column.
import {api, app, compareHash, esc, optHash, pageState, runHash, setTitle, signClass,
        statVal} from "../util.js";
import {renderRun} from "./run.js";
import {renderOptimization} from "./optimization.js";
import {renderCompare} from "./compare.js";

let shown = null;      // {project, data}: the project whose left column is on the page

export async function pageBacktest(project, query) {
  setTitle(`Backtest · ${project}`);
  const left = document.getElementById("bt-left");
  if (!shown || shown.project !== project || !left || !document.body.contains(left)) {
    await drawDashboard(project);
  }
  await drawRight(query);
}

async function drawDashboard(project) {
  const p = await api("/api/project", {name: project});
  shown = {project, data: p};
  app.innerHTML = `<div class="dashhead">
      <h1>${esc(p.name)} <span class="badge run">${esc(p.language)}</span></h1>
      <span class="muted">Backtest</span>
    </div>
    <div class="cols">
      <div id="bt-left" class="col-left"></div>
      <div id="bt-right" class="col-right"><p class="muted">Loading…</p></div>
    </div>`;
  drawLeft();
}

function runRow(r) {
  return `<tr data-ref="${esc(r.ref)}">
    <td><input type="checkbox" value="${esc(r.ref)}" aria-label="Select ${esc(r.name)} to compare"></td>
    <td><a href="${runHash(r.ref)}">${esc(r.name.replace(/^(\d{4})-(\d\d)-(\d\d)_(\d\d)-(\d\d)-\d\d_?/, "$2-$3 $4:$5 "))}</a>
      ${r.running ? '<span class="badge run">running</span>' : r.ok ? "" : `<span class="badge no" title="${esc(r.error)}">failed</span>`}
      <div class="muted small2">${esc(Object.entries(r.parameters || {}).map(([k, v]) => k + "=" + v).join(", "))}</div></td>
    <td class="num ${signClass(r.stats["Compounding Annual Return"])}">${esc(statVal(r.stats, "Compounding Annual Return"))}</td>
    <td class="num">${esc(statVal(r.stats, "Sharpe Ratio"))}</td>
    <td class="num">${esc(statVal(r.stats, "Drawdown"))}</td></tr>`;
}

function drawLeft() {
  const p = shown.data, el = document.getElementById("bt-left");
  el.innerHTML = `
    <details class="panel" open id="newbt"><summary><h2>New backtest</h2></summary>
      <label class="field">Name (optional)<input type="text" id="bname" placeholder="e.g. half-weight"></label>
      <div class="field">Parameters <a id="addp">+ add</a><div id="params"></div></div>
      <div class="field">Extra LEAN config <a id="addc">+ add</a><div id="extra"></div></div>
      <div class="row"><button id="go">Start backtest</button><span id="jobstate" class="muted">${pageState.lastJob && pageState.lastJob.project === p.name ? pageState.lastJob.html : ""}</span></div>
      <pre id="console" style="display:none;margin-top:10px"></pre>
    </details>
    <details class="panel" id="newopt"><summary><h2>New optimization (grid search)</h2></summary>
      <div class="field">Parameters: name, min, max, step <a id="addo">+ add</a><div id="oparams"></div></div>
      <div class="grid2">
        <label class="field">Target<input type="text" id="otarget" value="Sharpe Ratio"></label>
        <label class="field">Direction<select id="odir"><option value="max">maximize</option><option value="min">minimize</option></select></label>
      </div>
      <label class="field">Constraints, one per line (e.g. Drawdown &lt; 35)<textarea id="ocons" rows="2"></textarea></label>
      <div class="grid2">
        <label class="field">Name (optional)<input type="text" id="oname" placeholder="e.g. holdings"></label>
        <label class="field">Backtests at a time (0 = automatic)<input type="text" id="oconc" value="0"></label>
      </div>
      <div class="row"><button id="ogo">Start optimization</button><span id="ostate" class="muted"></span></div>
      <pre id="oconsole" style="display:none;margin-top:10px"></pre>
    </details>
    <div class="panel"><div class="row" style="justify-content:space-between"><h2>Runs (${p.runs.length})</h2>
        <button class="secondary" id="cmp" disabled>Compare selected</button></div>
      ${p.runs.length ? `<div class="scroll"><table class="runs"><tr><th></th><th>Run</th><th class="num">CAGR</th><th class="num">Sharpe</th><th class="num">DD</th></tr>
        ${p.runs.map(runRow).join("")}</table></div>` : '<p class="muted">No runs yet: start one above.</p>'}
    </div>
    ${p.optimizations.length ? `<div class="panel"><h2>Optimizations (${p.optimizations.length})</h2><table class="runs">
      <tr><th>Optimization</th><th>Best</th><th class="num">Runs</th></tr>
      ${p.optimizations.map(o => `<tr data-opt="${esc(o.name)}"><td><a href="${optHash(p.name, o.name)}">${esc(o.name)}</a>
          <div class="muted small2">${esc(o.direction)} ${esc(o.target)}</div></td>
        <td>${o.best ? esc(Object.entries(o.best.parameters).map(([k, v]) => k + "=" + v).join(", ")) + ` <span class="muted">(${esc(o.best.target)})</span>` : '<span class="muted">none met the constraints</span>'}</td>
        <td class="num">${o.runs}</td></tr>`).join("")}</table></div>` : ""}`;
  wireForms();
}

async function drawRight(query) {
  const el = document.getElementById("bt-right"), p = shown.data;
  const q = new URLSearchParams(query || "");
  const cmp = q.getAll("cmp"), opt = q.get("opt"), run = q.get("run") || (cmp.length || opt ? null : p.runs[0]?.ref);
  // highlight the selection in the left column and keep the compare boxes in step
  document.querySelectorAll("#bt-left tr[data-ref]").forEach(tr => tr.classList.toggle("sel", tr.dataset.ref === run));
  document.querySelectorAll("#bt-left tr[data-opt]").forEach(tr => tr.classList.toggle("sel", tr.dataset.opt === opt));
  document.querySelectorAll("#bt-left input[type=checkbox]").forEach(b => b.checked = cmp.includes(b.value));
  document.getElementById("cmp").disabled = cmp.length < 2;
  el.innerHTML = '<p class="muted">Loading…</p>';
  try {
    if (cmp.length >= 2) await renderCompare(el, cmp);
    else if (opt) await renderOptimization(el, p.name, opt);
    else if (run) await renderRun(el, run);
    else el.innerHTML = `<div class="panel"><h2>No backtests yet</h2><p class="muted">Start one with the form on the left
      (or <code>klean backtest ${esc(p.name)}</code>); its results appear here.</p></div>`;
  } catch (e) { el.innerHTML = `<div class="panel"><div class="err">${esc(e.message)}</div></div>`; }
}

function wireForms() {
  const p = shown.data, $ = id => document.getElementById(id);
  const kvRow = target => { const d = document.createElement("div"); d.className = "kv";
    d.innerHTML = `<input type="text" placeholder="name" aria-label="name"><input type="text" placeholder="value" aria-label="value"><a title="remove">✕</a>`;
    d.querySelector("a").onclick = () => d.remove(); $(target).appendChild(d); };
  const oRow = () => { const d = document.createElement("div"); d.className = "kv4";
    d.innerHTML = ["name", "min", "max", "step"].map(n => `<input type="text" placeholder="${n}" aria-label="${n}">`).join("") + '<a title="remove">✕</a>';
    d.querySelector("a").onclick = () => d.remove(); $("oparams").appendChild(d); };
  oRow();
  $("addp").onclick = () => kvRow("params");
  $("addc").onclick = () => kvRow("extra");
  $("addo").onclick = oRow;
  const collect = id => Object.fromEntries([...document.querySelectorAll(`#${id} .kv`)].map(d => [...d.querySelectorAll("input")].map(i => i.value.trim())).filter(([k]) => k));
  const boxes = () => [...document.querySelectorAll("#bt-left input[type=checkbox]:checked")].map(b => b.value);
  document.querySelectorAll("#bt-left input[type=checkbox]").forEach(b => b.onchange = () => $("cmp").disabled = boxes().length < 2);
  $("cmp").onclick = () => location.hash = compareHash(boxes());

  $("go").onclick = async () => {
    const btn = $("go"), state = $("jobstate"), con = $("console");
    btn.disabled = true; state.textContent = "starting…";
    try {
      const job = await api("/api/backtest", {}, {project: p.name, backtestName: $("bname").value.trim(),
        parameters: collect("params"), extraConfig: collect("extra")});
      con.style.display = "block";
      const poll = async () => {
        if (!document.body.contains(btn)) return;
        const j = await api("/api/job", {id: job.id});
        con.textContent = j.console.join("\n") || "(building…)"; con.scrollTop = con.scrollHeight;
        state.innerHTML = j.status === "done" ? `<span class="badge ok">done</span> <a href="${runHash(j.ref)}">open results</a>`
          : j.status === "failed" ? `<span class="badge no">failed</span> <span class="err">${esc(j.error.split("\n")[0])}</span>`
          : `<span class="badge run">${esc(j.status)}</span> ${Math.round(Date.now() / 1000 - j.started)} s`;
        if (j.status === "failed") { btn.disabled = false; con.textContent = j.error; return; }
        if (j.status === "done") {
          pageState.lastJob = {project: p.name, html: state.innerHTML};
          shown.data = await api("/api/project", {name: p.name});     // the new run in the list...
          drawLeft();
          location.hash = runHash(j.ref);                              // ...and its results on the right
          return;
        }
        setTimeout(poll, 1500);         // own timer: keeps going while other runs are opened
      };
      poll();
    } catch (e) { state.innerHTML = `<span class="err">${esc(e.message)}</span>`; btn.disabled = false; }
  };

  $("ogo").onclick = async () => {
    const btn = $("ogo"), state = $("ostate"), con = $("oconsole");
    const parameters = [...document.querySelectorAll("#oparams .kv4")].map(d => {
      const [name, min, max, step] = [...d.querySelectorAll("input")].map(i => i.value.trim()); return {name, min, max, step}; }).filter(x => x.name);
    btn.disabled = true; state.textContent = "starting…";
    try {
      const job = await api("/api/optimize", {}, {project: p.name, parameters, target: $("otarget").value.trim(),
        direction: $("odir").value, name: $("oname").value.trim(),
        constraints: $("ocons").value.split("\n").map(x => x.trim()).filter(Boolean),
        maxConcurrent: parseInt($("oconc").value, 10) || 0});
      con.style.display = "block";
      const poll = async () => {
        if (!document.body.contains(btn)) return;
        const j = await api("/api/job", {id: job.id});
        con.textContent = j.console.join("\n") || "(building…)"; con.scrollTop = con.scrollHeight;
        if (j.status === "running") {
          state.innerHTML = `<span class="badge run">running</span> ${job.backtests} backtests, ${Math.round(Date.now() / 1000 - j.started)} s`;
          setTimeout(poll, 1500); return;
        }
        btn.disabled = false;
        if (j.status !== "done") { state.innerHTML = `<span class="badge no">failed</span> <span class="err">${esc(j.error.split("\n")[0])}</span>`; return; }
        state.innerHTML = '<span class="badge ok">done</span>';
        shown.data = await api("/api/project", {name: p.name});
        drawLeft();
        location.hash = optHash(p.name, j.ref);
      };
      poll();
    } catch (e) { state.innerHTML = `<span class="err">${esc(e.message)}</span>`; btn.disabled = false; }
  };
}
