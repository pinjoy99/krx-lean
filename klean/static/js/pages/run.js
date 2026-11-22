import {COLORS, MAIN, TOKEN, api, app, compact, esc, fmtStat, full, href, setTitle, signClass, statVal, pageState, won} from "../util.js";
import {lineChart} from "../chart.js";

export async function pageRun(ref) {
  setTitle(ref);
  const r = await api("/api/run", {ref});
  const parts = r.ref.split("/"), project = parts[0];
  const optCrumb = parts[1] === "optimizations" ? ` <a href="${href("optimization", project, parts[2])}">optimization ${esc(parts[2])}</a> /` : "";
  const st = r.statistics, m = r.manifest || {};
  const tiles = MAIN.map(k => `<div class="tile"><div class="k">${esc(k)}</div><div class="v ${k === "Compounding Annual Return" || k === "Net Profit" ? signClass(st[k]) : ""}">${esc(statVal(st, k) || "—")}</div></div>`).join("");
  const statsRows = Object.entries(st).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${esc(fmtStat(k, v))}</td></tr>`).join("");
  const half = Math.ceil(Object.keys(st).length / 2), sr = statsRows.split("</tr>").filter(Boolean).map(x => x + "</tr>");
  const orders = r.orders.map(o => `<tr><td class="num">${o.id}</td><td>${esc((o.time || "").replace("T", " ").replace("Z", ""))}</td><td>${esc(o.symbol)}</td>
      <td>${esc(o.type)}</td><td class="num ${o.quantity < 0 ? "neg" : "pos"}">${full.format(o.quantity)}</td><td class="num">${full.format(o.price)}</td>
      <td class="num">${won(o.value)}</td><td>${esc(o.status)}</td><td class="muted">${esc(o.tag)}</td></tr>`).join("");
  app.innerHTML = `<div class="crumbs"><a href="#/">Workspace</a> / <a href="${href("project", project)}">${esc(project)}</a> /${optCrumb}</div>
    <h1>${esc(parts.at(-1))} ${r.demo ? '<span class="badge demo">SYNTHETIC DEMO DATA</span>' : ""}</h1>
    ${r.error ? `<div class="failbox"><span class="badge no">failed</span> This run did not complete: <pre class="err">${esc(r.error)}</pre>See the Log tab (LEAN console output) for details.</div>` : ""}
    <div class="row" style="margin-bottom:12px"><button class="secondary" id="mkreport">${r.report ? "Remake report" : "Make LEAN report"}</button>
      <a id="openreport" target="_blank" rel="noopener noreferrer" href="/report?${new URLSearchParams({ref: r.ref, token: TOKEN})}" style="${r.report ? "" : "display:none"}">Open report</a>
      <span id="repstate" class="muted"></span>
      ${parts[1] === "backtests" && !r.running ? '<span style="margin-left:auto"></span><button class="secondary" id="rename">Rename</button><button class="secondary" id="delete">Delete</button>' : ""}</div>
    ${r.running ? '<div class="panel"><span class="badge run">running</span> This backtest is still running; reload the page for its results.</div>' : ""}
    <div class="tiles">${tiles}</div>
    <div class="panel"><h2>Equity</h2><p class="muted small">KOSPI 200 scaled to the start equity. Drag across a chart to zoom, double-click to reset.</p><div id="eq"></div></div>
    <div class="panel"><h2>Drawdown</h2><div id="dd"></div></div>
    <div class="panel"><div class="tabs"><a data-t="stats" class="on">Statistics</a><a data-t="orders">Orders (${r.orders.length})</a><a data-t="log">Log</a><a data-t="code">Code (${r.code.length})</a><a data-t="manifest">Run record</a></div>
      <div data-p="stats" class="grid"><table>${sr.slice(0, half).join("")}</table><table>${sr.slice(half).join("")}</table></div>
      <div data-p="orders" style="display:none" class="scroll"><table><tr><th class="num">#</th><th>Time (UTC)</th><th>Symbol</th><th>Type</th><th class="num">Qty</th><th class="num">Price</th><th class="num">Value</th><th>Status</th><th>Tag</th></tr>${orders}</table></div>
      <div data-p="log" style="display:none"><pre>${esc(r.log.join("\n"))}</pre><div class="row" style="margin-top:8px"><a id="console">Show LEAN console output</a></div></div>
      <div data-p="code" style="display:none">${r.code.length ? `<p class="muted">The project's files as they were when this run started.</p>
        <div class="row" id="codefiles" style="flex-wrap:wrap;gap:6px 14px;margin-bottom:8px">${r.code.map(f => `<a data-f="${esc(f)}">${esc(f)}</a>`).join("")}</div><pre id="codetext"></pre>`
        : '<p class="muted">No code snapshot (run made before klean 0.5).</p>'}</div>
      <div data-p="manifest" style="display:none">${Object.keys(m).length ? `<table>${Object.entries(m).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${typeof v === "object" ? `<pre>${esc(JSON.stringify(v, null, 2))}</pre>` : esc(v)}</td></tr>`).join("")}</table>` : '<p class="muted">No manifest (run made before klean 0.2).</p>'}
        <p class="muted">Folder: ${esc(r.folder)}</p></div>
    </div>`;
  lineChart(document.getElementById("eq"), [{label: "Strategy", points: r.equity}, {label: "KOSPI 200", points: r.benchmark, color: COLORS[1], dashed: true}], {yFmt: v => "₩" + compact.format(v), log: true});
  lineChart(document.getElementById("dd"), [{label: "Drawdown", points: r.drawdown.map(([t, v]) => [t, -Math.abs(v)]), color: COLORS[5]}], {height: 160, yFmt: v => v.toFixed(1) + "%", area: true, zero: true});
  app.querySelectorAll(".tabs a").forEach(a => a.onclick = () => {
    app.querySelectorAll(".tabs a").forEach(x => x.classList.toggle("on", x === a));
    app.querySelectorAll("[data-p]").forEach(p => p.style.display = p.dataset.p === a.dataset.t ? (p.classList.contains("grid") ? "grid" : "block") : "none");
  });
  document.getElementById("console").onclick = async () => {
    const c = await api("/api/log", {ref, console: 1, tail: 400}); app.querySelector('[data-p="log"] pre').textContent = c.lines.join("\n"); };
  const showCode = async f => {
    const c = await api("/api/code-file", {ref: r.ref, path: f});
    app.querySelectorAll("#codefiles a").forEach(a => a.style.fontWeight = a.dataset.f === f ? "600" : "");
    document.getElementById("codetext").textContent = c.text ?? `(binary or large file, ${c.bytes} bytes)`;
  };
  app.querySelectorAll("#codefiles a").forEach(a => a.onclick = () => showCode(a.dataset.f));
  if (r.code.length) showCode(r.code.find(f => /^(main\.py|Main\.cs)$/.test(f)) || r.code[0]);
  const renameBtn = document.getElementById("rename");
  if (renameBtn) {
    renameBtn.onclick = async () => {
      const current = parts.at(-1).replace(/^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_?/, "");
      const name = prompt("Name for this run (the date and time stay in front):", current);
      if (name === null) return;
      try { const x = await api("/api/run-rename", {}, {ref: r.ref, name}); location.hash = href("run", x.ref).slice(1); }
      catch (e) { alert(e.message); }
    };
    document.getElementById("delete").onclick = async () => {
      if (!confirm(`Delete the run ${parts.at(-1)} and all its files? This can't be undone.`)) return;
      try { await api("/api/run-delete", {}, {ref: r.ref}); location.hash = href("project", project).slice(1); }
      catch (e) { alert(e.message); }
    };
  }
  document.getElementById("mkreport").onclick = async () => {
    const btn = document.getElementById("mkreport"), state = document.getElementById("repstate");
    btn.disabled = true; state.innerHTML = '<span class="badge run">making report</span> (about 40 s; LEAN replays the orders)';
    try {
      const job = await api("/api/report", {}, {ref: r.ref});
      const poll = async () => {
        if (!document.body.contains(btn)) return;   // left the page
        const j = await api("/api/job", {id: job.id});
        if (j.status === "running") {
          state.innerHTML = `<span class="badge run">making report</span> ${Math.round(Date.now() / 1000 - j.started)} s`;
          pageState.pollTimer = setTimeout(poll, 1500); return;
        }
        btn.disabled = false;
        if (j.status === "done") {
          btn.textContent = "Remake report"; document.getElementById("openreport").style.display = "";
          state.innerHTML = '<span class="badge ok">report ready</span>';
        } else state.innerHTML = `<span class="badge no">failed</span> <span class="err">${esc(j.error.split("\n")[0])}</span>`;
      };
      poll();
    } catch (e) { state.innerHTML = `<span class="err">${esc(e.message)}</span>`; btn.disabled = false; }
  };
}
