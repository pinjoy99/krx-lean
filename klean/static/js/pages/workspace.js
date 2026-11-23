// Workspace dashboard (the landing page). Left: projects, with their backtests and live
// paper trading deployments. Right: KRX data, setup check, settings.
import {api, app, backtestHash, esc, liveHash, researchHash, runHash, setTitle, signClass, statVal} from "../util.js";

function shortName(name) {
  return name.replace(/^(\d{4})-(\d\d)-(\d\d)_(\d\d)-(\d\d)-\d\d_?/, "$1-$2-$3 $4:$5 ").trim();
}

export async function pageWorkspace() {
  setTitle("Workspace");
  const w = await api("/api/workspace");
  document.getElementById("ws").textContent = w.root;
  const d = w.data || {};
  document.getElementById("demobar").hidden = !d.synthetic_demo_data;
  const proj = w.projects.map(p => {
    const cagr = p.last?.stats["Compounding Annual Return"];
    return `<tr>
      <td><a href="${researchHash(p.name)}" class="projlink">${esc(p.name)}</a><div class="muted small2">${esc(p.language)}</div></td>
      <td class="num">${p.runs}</td>
      <td>${p.last ? `<a href="${runHash(p.last.ref)}">${esc(shortName(p.last.name))}</a>
          ${p.last.ok ? `<span class="${signClass(cagr)}">${esc(statVal(p.last.stats, "Compounding Annual Return"))}</span>` : '<span class="badge no">failed</span>'}`
        : `<a href="${backtestHash(p.name)}" class="muted">none yet</a>`}</td>
      <td class="num">${p.live_runs ?? 0}</td>
      <td>${p.last_live ? `<a href="${liveHash(p.name, p.last_live.id)}">${esc(p.last_live.name)}</a> <span class="muted">${esc(p.last_live.status)}</span>
          <span class="${p.last_live.net_profit > 0 ? "pos" : p.last_live.net_profit < 0 ? "neg" : ""}">${(p.last_live.net_profit > 0 ? "+" : "") + p.last_live.net_profit.toFixed(2)}%</span>`
        : `<a href="${liveHash(p.name)}" class="muted">none yet</a>`}</td></tr>`;
  }).join("");
  const doctor = w.doctor.map(r => `<tr><td>${r.ok ? '<span class="badge ok">OK</span>' : '<span class="badge no">NO</span>'}</td><td style="overflow-wrap:normal;min-width:9em">${esc(r.item)}</td><td class="muted">${esc(r.detail)}</td></tr>`).join("");
  const idx = Object.entries(d.indices || {}).map(([k, v]) => `${esc(k)} ${v.first}→${v.last}`).join(", ");
  app.innerHTML = `<div class="dashhead"><h1>Workspace</h1></div>
    <div class="cols wide-left">
      <div class="col-left">
        <div class="panel"><h2>Projects</h2>${w.projects.length ? `<p class="muted small">Open a project's research notebook by its name; its backtests and live runs from their columns.</p>
          <div class="scroll"><table class="runs"><tr><th>Project</th><th class="num">Backtests</th><th>Last backtest</th><th class="num">Live runs</th><th>Last live run</th></tr>${proj}</table></div>`
          : `<p class="muted">No projects yet. Create one with <code>klean create-project NAME</code> (templates: ${w.templates.map(esc).join(", ")}).</p>`}</div>
      </div>
      <div class="col-right">
        <div class="panel"><h2>KRX data</h2>${d.error ? `<div class="err">${esc(d.error)}</div>` : `<table>
          <tr><td>Securities</td><td class="num">${d.securities ?? "—"}</td></tr>
          <tr><td>Dates</td><td class="num">${d.first_date ?? "—"} → ${d.last_date ?? "—"}</td></tr>
          <tr><td>Active on last date</td><td class="num">${d.active ?? "—"} ${d.active_by_market ? `<span class="muted">(${Object.entries(d.active_by_market).map(([k, v]) => esc(k) + " " + v).join(", ")})</span>` : ""}</td></tr>
          <tr><td>Delisted / suspended</td><td class="num">${d.delisted_or_suspended ?? "—"}</td></tr>
          <tr><td>Universe files</td><td class="num">${d.universe_files ? `${d.universe_files.count} (${d.universe_files.first} → ${d.universe_files.last})` : "—"}</td></tr>
          <tr><td>Indices</td><td class="num">${idx || "—"}</td></tr>
          <tr><td>Equity-krx market hours</td><td class="num">${d.market_hours?.installed ? `installed, ${d.market_hours.holidays} holidays` : '<span class="neg">missing — klean install data</span>'}</td></tr></table>`}</div>
        <div class="panel"><h2>Setup check</h2><table>${doctor}</table></div>
        <div class="panel"><h2>Settings</h2><table>
          <tr><td>LEAN</td><td>${esc(w.lean_root)}</td></tr><tr><td>Python env</td><td>${esc(w.python_venv || "—")}</td></tr>
          ${Object.entries(w.lean_config).map(([k, v]) => `<tr><td>${esc(k)} <span class="muted">(LEAN config)</span></td><td>${esc(v)}</td></tr>`).join("")}
          <tr><td>klean</td><td>${esc(w.version)}</td></tr></table></div>
      </div>
    </div>`;
}
