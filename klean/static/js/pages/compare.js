import {COLORS, api, app, compact, esc, fmtStat, href, setTitle, statVal} from "../util.js";
import {lineChart} from "../chart.js";

export async function pageCompare(refs) {
  setTitle("Compare");
  if (refs.length < 2) {
    const w = await api("/api/workspace");
    const lists = await Promise.all(w.projects.filter(p => p.runs).map(p => api("/api/project", {name: p.name})));
    const rows = lists.flatMap(p => p.runs.filter(r => r.ok).map(r => `<tr><td><input type="checkbox" value="${esc(r.ref)}"></td><td>${esc(p.name)}</td>
        <td><a href="${href("run", r.ref)}">${esc(r.name)}</a></td><td class="num">${esc(r.stats["Compounding Annual Return"])}</td><td class="num">${esc(statVal(r.stats, "End Equity"))}</td></tr>`)).join("");
    app.innerHTML = `<h1>Compare runs</h1><div class="panel"><div class="row" style="justify-content:space-between"><h2>Choose two or more runs</h2><button id="cmp" disabled>Compare</button></div>
      <div class="scroll"><table><tr><th></th><th>Project</th><th>Run</th><th class="num">CAGR</th><th class="num">End equity</th></tr>${rows}</table></div></div>`;
    const boxes = () => [...app.querySelectorAll("input:checked")].map(b => b.value);
    app.querySelectorAll("input").forEach(b => b.onchange = () => document.getElementById("cmp").disabled = boxes().length < 2);
    document.getElementById("cmp").onclick = () => location.hash = "#/compare?" + boxes().map(r => "ref=" + encodeURIComponent(r)).join("&");
    return;
  }
  const c = await api("/api/compare", {ref: refs, all: 1});
  const v = c.verdict;
  const head = c.header.slice(1, -1).map((h, i) => `<th class="num"><a href="${href("run", c.refs[i])}" style="color:${COLORS[i % COLORS.length]}">${esc(h)}</a></th>`).join("");
  const rows = c.rows.map(r => `<tr class="${r.at(-1) ? "diff" : ""}"><td>${esc(r[0])}</td>${r.slice(1, -1).map(x => `<td class="num">${esc(fmtStat(r[0], x))}</td>`).join("")}<td>${esc(r.at(-1))}</td></tr>`).join("");
  app.innerHTML = `<div class="crumbs"><a href="#/compare">Compare</a> /</div>
    <h1>Comparison ${v.identical ? '<span class="badge ok">IDENTICAL</span>' : '<span class="badge no">DIFFERENT</span>'}</h1>
    <p class="muted">Equity curves: ${v.equity_curves_identical === true ? "identical" : v.equity_curves_identical === false ? "different" : "not available"}${v.differing.length ? " · differing statistics: " + v.differing.map(esc).join(", ") : ""}</p>
    <div class="panel"><h2>Equity</h2><p class="muted small">Drag across the chart to zoom, double-click to reset.</p><div id="eq"></div></div>
    <div class="panel"><h2>Statistics</h2><div class="scroll"><table><tr><th>Statistic</th>${head}<th></th></tr>${rows}</table></div></div>`;
  lineChart(document.getElementById("eq"), c.curves.map((cv, i) => ({label: cv.label, points: cv.points, dashed: i > 0})), {yFmt: v => "₩" + compact.format(v), log: true});
}
