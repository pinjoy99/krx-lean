import {api, app, esc, href, setTitle, signClass, statVal, pageState} from "../util.js";

export async function pageProject(name) {
  setTitle(name);
  const p = await api("/api/project", {name});
  const rows = p.runs.map(r => `<tr><td><input type="checkbox" value="${esc(r.ref)}"></td>
      <td><a href="${href("run", r.ref)}">${esc(r.name)}</a> ${r.running ? '<span class="badge run">running</span>' : r.ok ? "" : `<span class="badge no" title="${esc(r.error)}">failed</span>`}${r.demo ? ' <span class="badge demo">demo</span>' : ""}</td>
      <td class="muted">${esc(Object.entries(r.parameters || {}).map(([k, v]) => k + "=" + v).join(", "))}</td>
      ${["Compounding Annual Return", "Drawdown", "Sharpe Ratio", "Total Orders", "End Equity"].map(k => `<td class="num ${k === "Compounding Annual Return" ? signClass(r.stats[k]) : ""}">${esc(statVal(r.stats, k))}</td>`).join("")}
      <td class="num muted">${r.seconds != null ? r.seconds + " s" : ""}</td></tr>`).join("");
  app.innerHTML = `<div class="crumbs"><a href="#/">Workspace</a> /</div><h1>${esc(p.name)} <span class="badge run">${esc(p.language)}</span></h1>
    <div class="panel"><h2>Run a backtest</h2>
      <div class="grid" style="grid-template-columns: 1fr 1fr 1fr">
        <div><div class="muted">Backtest name (optional)</div><input type="text" id="bname" placeholder="e.g. half-weight"></div>
        <div><div class="muted">Parameters <a id="addp">+ add</a></div><div id="params"></div></div>
        <div><div class="muted">Extra LEAN config <a id="addc">+ add</a></div><div id="extra"></div></div>
      </div>
      <div class="row" style="margin-top:10px"><button id="go">Start backtest</button><span id="jobstate" class="muted">${pageState.lastJob && pageState.lastJob.project === p.name ? pageState.lastJob.html : ""}</span></div>
      <pre id="console" style="display:none;margin-top:10px"></pre>
    </div>
    <div class="panel"><div class="row" style="justify-content:space-between"><h2>Runs (${p.runs.length})</h2>
      <button class="secondary" id="cmp" disabled>Compare selected</button></div>
      ${p.runs.length ? `<div class="scroll"><table><tr><th></th><th>Run</th><th>Parameters</th><th class="num">CAGR</th><th class="num">Drawdown</th><th class="num">Sharpe</th><th class="num">Orders</th><th class="num">End equity</th><th class="num">Time</th></tr>${rows}</table></div>` : '<p class="muted">No runs yet.</p>'}
    </div>
    ${p.optimizations.length ? `<div class="panel"><h2>Optimizations (${p.optimizations.length})</h2><table>
      <tr><th>Optimization</th><th>Target</th><th class="num">Backtests</th><th>Best parameters</th><th class="num">Best value</th><th class="num">Time</th></tr>
      ${p.optimizations.map(o => `<tr><td><a href="${href("optimization", p.name, o.name)}">${esc(o.name)}</a></td><td>${esc(o.direction)} ${esc(o.target)}</td>
        <td class="num">${o.runs}</td><td>${o.best ? esc(Object.entries(o.best.parameters).map(([k, v]) => k + "=" + v).join(", ")) : '<span class="muted">none met the constraints</span>'}</td>
        <td class="num">${o.best ? esc(o.best.target) : ""}</td><td class="num muted">${o.seconds != null ? o.seconds + " s" : ""}</td></tr>`).join("")}</table>
      </div>` : ""}
    <div class="panel"><h2>Optimize (grid search)</h2>
      <div class="grid" style="grid-template-columns: 2fr 1fr">
        <div><div class="muted">Parameters: name, min, max, step <a id="addo">+ add</a></div><div id="oparams"></div></div>
        <div><div class="muted">Target</div><input type="text" id="otarget" value="Sharpe Ratio">
          <select id="odir" style="margin-top:6px"><option value="max">maximize</option><option value="min">minimize</option></select></div>
      </div>
      <div class="grid" style="grid-template-columns: 2fr 1fr; margin-top:8px">
        <div><div class="muted">Constraints, one per line (e.g. Drawdown &lt; 35)</div><textarea id="ocons" rows="2" style="width:100%"></textarea></div>
        <div><div class="muted">Name (optional)</div><input type="text" id="oname" placeholder="e.g. holdings">
          <div class="muted" style="margin-top:6px">Backtests at a time (0 = automatic)</div><input type="text" id="oconc" value="0"></div>
      </div>
      <div class="row" style="margin-top:10px"><button id="ogo">Start optimization</button><span id="ostate" class="muted"></span></div>
      <pre id="oconsole" style="display:none;margin-top:10px"></pre>
    </div>
    <div class="panel"><h2>Research notebook</h2>
      <div class="row"><button class="secondary" id="nb">Start JupyterLab for this project</button><span id="nbstate" class="muted">
        LEAN's QuantBook on this workspace's data; the first start installs JupyterLab (a few minutes).</span></div></div>
    <div class="panel"><h2>Files</h2><div class="muted">${p.files.map(esc).join(" · ")}</div></div>`;
  const oRow = () => { const d = document.createElement("div"); d.className = "kv4";
    d.innerHTML = `<input type="text" placeholder="name"><input type="text" placeholder="min"><input type="text" placeholder="max"><input type="text" placeholder="step"><a title="remove">✕</a>`;
    d.querySelector("a").onclick = () => d.remove(); document.getElementById("oparams").appendChild(d); };
  oRow();
  document.getElementById("addo").onclick = oRow;
  document.getElementById("ogo").onclick = async () => {
    const btn = document.getElementById("ogo"), state = document.getElementById("ostate"), con = document.getElementById("oconsole");
    const parameters = [...document.querySelectorAll("#oparams .kv4")].map(d => { const [name, min, max, step] = [...d.querySelectorAll("input")].map(i => i.value.trim()); return {name, min, max, step}; }).filter(x => x.name);
    btn.disabled = true; state.textContent = "starting…";
    try {
      const job = await api("/api/optimize", {}, {project: p.name, parameters, target: document.getElementById("otarget").value.trim(),
        direction: document.getElementById("odir").value, name: document.getElementById("oname").value.trim(),
        constraints: document.getElementById("ocons").value.split("\n").map(x => x.trim()).filter(Boolean),
        maxConcurrent: parseInt(document.getElementById("oconc").value, 10) || 0});
      con.style.display = "block";
      const poll = async () => {
        if (!document.body.contains(btn)) return;
        const j = await api("/api/job", {id: job.id});
        con.textContent = j.console.join("\n") || "(building…)"; con.scrollTop = con.scrollHeight;
        if (j.status === "running") {
          state.innerHTML = `<span class="badge run">running</span> ${job.backtests} backtests, ${Math.round(Date.now() / 1000 - j.started)} s`;
          pageState.pollTimer = setTimeout(poll, 1500); return;
        }
        btn.disabled = false;
        state.innerHTML = j.status === "done" ? `<span class="badge ok">done</span> <a href="${href("optimization", p.name, j.ref)}">open the results</a>`
          : `<span class="badge no">failed</span> <span class="err">${esc(j.error.split("\n")[0])}</span>`;
      };
      poll();
    } catch (e) { state.innerHTML = `<span class="err">${esc(e.message)}</span>`; btn.disabled = false; }
  };
  document.getElementById("nb").onclick = async () => {
    const btn = document.getElementById("nb"), state = document.getElementById("nbstate");
    btn.disabled = true; state.innerHTML = '<span class="badge run">starting</span> (the first time this installs JupyterLab)';
    try {
      const r = await api("/api/research", {}, {project: p.name});
      state.innerHTML = `<span class="badge ok">${r.started ? "started" : "already running"}</span> <a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">Open the notebook</a> (give it a few seconds; it stops when klean gui stops)`;
    } catch (e) { state.innerHTML = `<span class="err">${esc(e.message)}</span>`; }
    btn.disabled = false;
  };
  const kvRow = target => { const d = document.createElement("div"); d.className = "kv";
    d.innerHTML = `<input type="text" placeholder="name"><input type="text" placeholder="value"><a title="remove">✕</a>`;
    d.querySelector("a").onclick = () => d.remove(); document.getElementById(target).appendChild(d); };
  document.getElementById("addp").onclick = () => kvRow("params");
  document.getElementById("addc").onclick = () => kvRow("extra");
  const collect = id => Object.fromEntries([...document.querySelectorAll(`#${id} .kv`)].map(d => [...d.querySelectorAll("input")].map(i => i.value.trim())).filter(([k]) => k));
  const boxes = () => [...app.querySelectorAll("input[type=checkbox]:checked")].map(b => b.value);
  app.querySelectorAll("input[type=checkbox]").forEach(b => b.onchange = () => document.getElementById("cmp").disabled = boxes().length < 2);
  document.getElementById("cmp").onclick = () => location.hash = "#/compare?" + boxes().map(r => "ref=" + encodeURIComponent(r)).join("&");
  document.getElementById("go").onclick = async () => {
    const btn = document.getElementById("go"), state = document.getElementById("jobstate"), con = document.getElementById("console");
    btn.disabled = true; state.textContent = "starting…";
    try {
      const job = await api("/api/backtest", {}, {project: p.name, backtestName: document.getElementById("bname").value.trim(),
        parameters: collect("params"), extraConfig: collect("extra")});
      con.style.display = "block";
      const poll = async () => {
        const j = await api("/api/job", {id: job.id});
        con.textContent = j.console.join("\n") || "(building…)"; con.scrollTop = con.scrollHeight;
        state.innerHTML = j.status === "done" ? `<span class="badge ok">done</span> <a href="${href("run", j.ref)}">open results</a>`
          : j.status === "failed" ? `<span class="badge no">failed</span> <span class="err">${esc(j.error.split("\n")[0])}</span>`
          : `<span class="badge run">${esc(j.status)}</span> ${Math.round(Date.now() / 1000 - j.started)} s`;
        if (j.status === "done" || j.status === "failed") {
          btn.disabled = false;
          if (j.status === "failed") { con.textContent = j.error; return; }
          pageState.lastJob = {project: p.name, html: state.innerHTML};
          if (location.hash.startsWith("#/project/")) pageProject(p.name);   // refresh the runs list
          return;
        }
        pageState.pollTimer = setTimeout(poll, 1500);
      };
      poll();
    } catch (e) { state.innerHTML = `<span class="err">${esc(e.message)}</span>`; btn.disabled = false; }
  };
}
