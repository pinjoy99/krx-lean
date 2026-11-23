import {COLORS, api, esc, fmtStat, runHash, wireCompare} from "../util.js";
import {lineChart} from "../chart.js";

// An optimization's results, in the Backtest dashboard's right column.
export async function renderOptimization(el, project, name) {
  const o = await api("/api/optimization", {project, name});
  const params = o.parameters.map(p => `${esc(p.name)} ${esc(p.min)}…${esc(p.max)} step ${esc(p.step)}`).join(", ");
  const head = o.header.map((h, i) => `<th class="${i > o.parameters.length ? "num" : ""}">${esc(h)}</th>`).join("");
  const rows = o.rows.map((r, i) => `<tr><td><input type="checkbox" value="${esc(o.row_refs[i])}"></td>${r.map((x, j) =>
      j === 0 ? `<td>${x ? '<span class="badge ok">best</span>' : ""}</td>`
      : j === r.length - 1 ? `<td class="${x === "ok" ? "" : "neg"}">${esc(x)}</td>`
      : `<td class="${j > o.parameters.length ? "num" : ""}">${j === 1 ? `<a href="${runHash(o.row_refs[i])}">${esc(x)}</a>` : esc(j === r.length - 2 ? fmtStat("End Equity", x) : x)}</td>`).join("")}</tr>`).join("");
  el.innerHTML = `<h2 class="runtitle">Optimization ${esc(name)}</h2>
    <p class="muted">${esc(o.direction)} <b>${esc(o.target)}</b> · grid over ${params}${o.constraints.length ? " · constraints: " + o.constraints.map(esc).join(", ") : ""} · ${o.runs.length} backtests, ${o.concurrent} at a time, ${o.seconds} s</p>
    ${o.parameters.length === 1 ? `<div class="panel"><h2>${esc(o.target)} by ${esc(o.parameters[0].name)}</h2><p class="muted small">Hollow points fail the constraints.</p><div id="pc"></div></div>` : ""}
    <div class="panel"><div class="row" style="justify-content:space-between"><h2>Results (best first)</h2><button class="secondary" id="ocmp" disabled>Compare selected</button></div>
      <div class="scroll"><table><tr><th></th>${head}</tr>${rows}</table></div></div>`;
  if (o.parameters.length === 1) {
    const pname = o.parameters[0].name;
    const pts = o.points.filter(p => p[1] != null).map(([ps, v, ok]) => [parseFloat(ps[pname]), v, ok]).sort((a, b) => a[0] - b[0]);
    const failing = pts.filter(p => p[2] === false);
    lineChart(el.querySelector("#pc"), [{label: o.target, points: pts},
      ...(failing.length ? [{label: "fails the constraints", points: failing, color: COLORS[0], hollow: true, line: false}] : [])],
      {height: 220, dots: true, time: false, yFmt: v => (+v.toPrecision(4)).toString(),
       xFmt: v => (+v.toPrecision(6)).toString(), xTip: v => String(+v.toPrecision(6)), xLabel: pname,
       xTicks: [...new Set(pts.map(p => p[0]))]});
  }
  wireCompare(el, el.querySelector("#ocmp"));
}
