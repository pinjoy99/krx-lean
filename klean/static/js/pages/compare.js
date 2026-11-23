import {COLORS, api, compact, esc, fmtStat, runHash} from "../util.js";
import {lineChart} from "../chart.js";

// Two or more runs side by side, in the Backtest dashboard's right column.
export async function renderCompare(el, refs) {
  const c = await api("/api/compare", {ref: refs, all: 1});
  const v = c.verdict;
  const head = c.header.slice(1, -1).map((h, i) => `<th class="num"><a href="${runHash(c.refs[i])}" style="color:${COLORS[i % COLORS.length]}">${esc(h)}</a></th>`).join("");
  const rows = c.rows.map(r => `<tr class="${r.at(-1) ? "diff" : ""}"><td>${esc(r[0])}</td>${r.slice(1, -1).map(x => `<td class="num">${esc(fmtStat(r[0], x))}</td>`).join("")}<td>${esc(r.at(-1))}</td></tr>`).join("");
  el.innerHTML = `<h2 class="runtitle">Comparison of ${refs.length} runs ${v.identical ? '<span class="badge ok">IDENTICAL</span>' : '<span class="badge no">DIFFERENT</span>'}</h2>
    <p class="muted">Equity curves: ${v.equity_curves_identical === true ? "identical" : v.equity_curves_identical === false ? "different" : "not available"}${v.differing.length ? " · differing statistics: " + v.differing.map(esc).join(", ") : ""}</p>
    <div class="panel"><h2>Equity</h2><p class="muted small">Drag across the chart to zoom, double-click to reset.</p><div id="eq"></div></div>
    <div class="panel"><h2>Statistics</h2><div class="scroll"><table><tr><th>Statistic</th>${head}<th></th></tr>${rows}</table></div></div>`;
  lineChart(el.querySelector("#eq"), c.curves.map((cv, i) => ({label: cv.label, points: cv.points, dashed: i > 0})), {yFmt: v => "₩" + compact.format(v), log: true});
}
