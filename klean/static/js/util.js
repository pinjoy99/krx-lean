// Shared helpers for the klean GUI pages.

export const TOKEN = new URLSearchParams(location.search).get("token") || "";
export const app = document.getElementById("app");
export const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export const COLORS = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6"].map(cssVar);
export const MAIN = ["Compounding Annual Return", "Drawdown", "Sharpe Ratio", "Net Profit", "Total Fees", "End Equity", "Total Orders"];

// Page-level state that survives re-rendering a page.
export const pageState = {
  pollTimer: null,
  lastJob: null,   // the latest backtest started from a project page, shown after the page refreshes
  stale: false,    // the shown project's runs changed (a run deleted or renamed): reload them
};

// Go to a dashboard address, redrawing it even when it's the address already shown.
export function go(hash) {
  if (location.hash === hash) window.dispatchEvent(new HashChangeEvent("hashchange"));
  else location.hash = hash;
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}

export async function api(path, params = {}, body = null) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) (Array.isArray(v) ? v : [v]).forEach(x => qs.append(k, x));
  const res = await fetch(path + (qs.toString() ? "?" + qs : ""), {
    method: body ? "POST" : "GET", headers: {"X-Klean-Token": TOKEN, "Content-Type": "application/json"},
    body: body ? JSON.stringify(body) : null});
  const data = await res.json().catch(() => ({error: res.statusText}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

export const compact = new Intl.NumberFormat("en", {notation: "compact", maximumFractionDigits: 2});
export const full = new Intl.NumberFormat("en", {maximumFractionDigits: 2});
export function won(v) { const n = Math.round(v); return (n < 0 ? "−₩" : "₩") + full.format(Math.abs(n)); }
export function day(t) { return new Date(t * 1000).toISOString().slice(0, 10); }
export function signClass(s) {
  const n = parseFloat(String(s).replace(/[^0-9.\-]/g, ""));
  return isNaN(n) ? "" : n < 0 ? "neg" : n > 0 ? "pos" : "";
}
const WON_KEYS = new Set(["End Equity", "Start Equity", "Total Fees"]);
export function fmtStat(k, v) {
  if (v === "" || v == null || !WON_KEYS.has(k)) return v ?? "";
  const n = parseFloat(String(v).replace(/[^0-9.\-]/g, ""));
  return isNaN(n) ? v : won(n);
}
export function statVal(stats, k) { return fmtStat(k, stats?.[k]); }
export function href(...parts) { return "#/" + parts.map(encodeURIComponent).join("/"); }
export function setTitle(t) { document.title = t ? `${t} · klean` : "klean"; }
export function showError(e) {
  app.innerHTML = `<div class="panel"><h2>Error</h2><div class="err">${esc(e.message || e)}</div></div>`;
}
// Dashboard addresses: #/backtest/P[?run=REF | ?opt=NAME | ?cmp=REF&cmp=REF], #/research/P, #/live/P[?test=ID]
const projectOf = ref => ref.split("/")[0];
export function backtestHash(project) { return href("backtest", project); }
export function runHash(ref) { return `${backtestHash(projectOf(ref))}?run=${encodeURIComponent(ref)}`; }
export function optHash(project, name) { return `${backtestHash(project)}?opt=${encodeURIComponent(name)}`; }
export function compareHash(refs) {
  return `${backtestHash(projectOf(refs[0]))}?` + refs.map(r => "cmp=" + encodeURIComponent(r)).join("&");
}
export function researchHash(project) { return href("research", project); }
export function liveHash(project, test = "") { return href("live", project) + (test ? `?test=${encodeURIComponent(test)}` : ""); }
// Checkbox lists with a "Compare selected" button.
export function wireCompare(root, button) {
  const boxes = () => [...root.querySelectorAll("input[type=checkbox]:checked")].map(b => b.value);
  root.querySelectorAll("input[type=checkbox]").forEach(b => b.onchange = () => button.disabled = boxes().length < 2);
  button.onclick = () => location.hash = compareHash(boxes());
}
