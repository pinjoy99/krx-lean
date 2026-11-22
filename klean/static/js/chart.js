// Line charts on uPlot: zoom by dragging (double-click resets), values follow the cursor in
// the legend, optional log scale. Series are [{label, points: [[x, y(, ok)], ...], color, dashed}].
import uPlot from "../vendor/uplot/uPlot.esm.js";
import {COLORS, compact, cssVar, day} from "./util.js";

function aligned(seriesList) {
  // uPlot wants one x array; series may have different dates (strategy vs benchmark).
  const tables = seriesList.map(s => [s.points.map(p => p[0]), s.points.map(p => p[1])]);
  return tables.length === 1 ? tables[0] : uPlot.join(tables);
}

function alpha(color, a) {
  const m = color.match(/^#([0-9a-f]{6})$/i);
  if (!m) return color;
  const n = parseInt(m[1], 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

// A y range that includes 0 (drawdowns), padded on the side away from 0.
function zeroRange(u, lo, hi) {
  lo = Math.min(lo, 0); hi = Math.max(hi, 0);
  const pad = (hi - lo) * 0.05 || 1;
  return [lo === 0 ? 0 : lo - pad, hi === 0 ? 0 : hi + pad];
}

/**
 * @param {HTMLElement} el
 * @param {Array} seriesList
 * @param {object} opts height, yFmt, xFmt (axis), xTip (legend), area, zero, dots, time (x is a
 *   date in seconds; default true), log (offer a log-scale checkbox)
 */
export function lineChart(el, seriesList, {height = 280, yFmt = v => compact.format(v), xFmt = null, xTip = null,
                                           area = false, zero = false, dots = false, time = true, log = false,
                                           xLabel = null, xTicks = null} = {}) {
  el.classList.add("chart");
  if (!seriesList.some(s => s.points.length)) { el.innerHTML = `<p class="muted">No data.</p>`; return null; }
  const muted = cssVar("--muted"), grid = cssVar("--grid");
  const tipX = xTip || (time ? t => day(t) : v => String(+v.toPrecision(6)));
  let logScale = false, plot = null;

  const build = () => {
    const series = [{label: xLabel || (time ? "Date" : "x"), value: (u, v) => v == null ? "—" : tipX(v)}];
    seriesList.forEach((s, i) => {
      const c = s.color || COLORS[i % COLORS.length];
      series.push({label: s.label, stroke: c, width: 1.6, spanGaps: true,
                   ...(s.dashed ? {dash: [5, 4]} : {}), ...(area ? {fill: alpha(c, 0.15)} : {}),
                   value: (u, v) => v == null ? "—" : yFmt(v),
                   points: dots ? {show: true, size: s.hollow ? 11 : 8, width: 1.6, fill: s.hollow ? cssVar("--panel") : c}
                                : {show: false},
                   ...(s.line === false ? {paths: () => null} : {})});
    });
    const data = aligned(seriesList);
    const axis = {stroke: muted, grid: {stroke: grid, width: 1}, ticks: {stroke: grid, width: 1}, font: "11px system-ui, sans-serif"};
    const opts = {
      width: Math.max(el.clientWidth, 300), height,
      series,
      scales: {x: {time}, y: {distr: logScale ? 3 : 1, ...(zero && !logScale ? {range: zeroRange} : {})}},
      axes: [{...axis, ...(xFmt ? {values: (u, vals) => vals.map(xFmt)} : {}), ...(xTicks ? {splits: () => xTicks} : {})},
             {...axis, size: 70, values: (u, vals) => vals.map(v => yFmt(v))}],
      cursor: {drag: {x: true, y: false}, points: {size: 7}},
      legend: {live: true},
    };
    if (time) opts.tzDate = ts => uPlot.tzDate(new Date(ts * 1e3), "Etc/UTC");
    if (plot) plot.destroy();
    // The legend shows the latest values while the cursor isn't on the chart.
    const latest = u => { if (u.cursor.idx == null) u.setLegend({idx: data[0].length - 1}); };
    opts.hooks = {ready: [latest], setCursor: [latest]};
    plot = new uPlot(opts, data, holder);
    el.uplot = plot;                                  // for tests and the browser console
  };

  el.innerHTML = log ? `<label class="chartopt"><input type="checkbox"> log scale</label>` : "";
  const holder = document.createElement("div");
  el.appendChild(holder);
  if (log) el.querySelector(".chartopt input").onchange = e => { logScale = e.target.checked; build(); };
  build();
  new ResizeObserver(() => plot && plot.setSize({width: Math.max(el.clientWidth, 300), height})).observe(el);
  return plot;
}
