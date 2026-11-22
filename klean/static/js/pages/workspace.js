import {api, app, esc, href, setTitle, signClass, statVal} from "../util.js";

export async function pageWorkspace() {
  setTitle("Workspace");
  const w = await api("/api/workspace");
  document.getElementById("ws").textContent = w.root;
  const d = w.data || {};
  document.getElementById("demobar").hidden = !d.synthetic_demo_data;
  const proj = w.projects.map(p => `<tr><td><a href="${href("project", p.name)}">${esc(p.name)}</a></td><td>${esc(p.language)}</td>
      <td class="num">${p.runs}</td>
      <td>${p.last ? `<a href="${href("run", p.last.ref)}">${esc(p.last.name)}</a>` : '<span class="muted">—</span>'}</td>
      ${["Compounding Annual Return", "Drawdown", "Sharpe Ratio", "End Equity"].map(k => `<td class="num ${k === "Compounding Annual Return" ? signClass(p.last?.stats[k]) : ""}">${esc(p.last ? statVal(p.last.stats, k) : "")}</td>`).join("")}</tr>`).join("");
  const doctor = w.doctor.map(r => `<tr><td>${r.ok ? '<span class="badge ok">OK</span>' : '<span class="badge no">NO</span>'}</td><td style="overflow-wrap:normal;min-width:9em">${esc(r.item)}</td><td class="muted">${esc(r.detail)}</td></tr>`).join("");
  const idx = Object.entries(d.indices || {}).map(([k, v]) => `${esc(k)} ${v.first}→${v.last}`).join(", ");
  app.innerHTML = `<h1>Workspace</h1>
    <div class="panel"><h2>Projects</h2>${w.projects.length ? `<table><tr><th>Project</th><th>Language</th><th class="num">Runs</th><th>Last run</th>
      <th class="num">CAGR</th><th class="num">Drawdown</th><th class="num">Sharpe</th><th class="num">End equity</th></tr>${proj}</table>`
      : `<p class="muted">No projects yet. Create one with <code>klean create-project NAME</code> (templates: ${w.templates.map(esc).join(", ")}).</p>`}</div>
    <div class="grid">
      <div class="panel"><h2>KRX data</h2>${d.error ? `<div class="err">${esc(d.error)}</div>` : `<table>
        <tr><td>Securities</td><td class="num">${d.securities ?? "—"}</td></tr>
        <tr><td>Dates</td><td class="num">${d.first_date ?? "—"} → ${d.last_date ?? "—"}</td></tr>
        <tr><td>Active on last date</td><td class="num">${d.active ?? "—"} ${d.active_by_market ? `<span class="muted">(${Object.entries(d.active_by_market).map(([k, v]) => esc(k) + " " + v).join(", ")})</span>` : ""}</td></tr>
        <tr><td>Delisted / suspended</td><td class="num">${d.delisted_or_suspended ?? "—"}</td></tr>
        <tr><td>Universe files</td><td class="num">${d.universe_files ? `${d.universe_files.count} (${d.universe_files.first} → ${d.universe_files.last})` : "—"}</td></tr>
        <tr><td>Indices</td><td class="num">${idx || "—"}</td></tr>
        <tr><td>Equity-krx market hours</td><td class="num">${d.market_hours?.installed ? `installed, ${d.market_hours.holidays} holidays` : '<span class="neg">missing — klean install data</span>'}</td></tr></table>`}</div>
      <div class="panel"><h2>Setup check</h2><table>${doctor}</table></div>
    </div>
    <div class="panel"><h2>Settings</h2><table>
      <tr><td>LEAN</td><td>${esc(w.lean_root)}</td></tr><tr><td>Python env</td><td>${esc(w.python_venv || "—")}</td></tr>
      ${Object.entries(w.lean_config).map(([k, v]) => `<tr><td>${esc(k)} <span class="muted">(LEAN config)</span></td><td>${esc(v)}</td></tr>`).join("")}
      <tr><td>klean</td><td>${esc(w.version)}</td></tr></table></div>`;
}
