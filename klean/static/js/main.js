// klean GUI: hash router. Dashboards: #/ (workspace), #/research/P[?open=new], #/backtest/P[?run=|?opt=|?cmp=…], #/live/P. Pages live in ./pages/, one module each.
import {TOKEN, api, compareHash, optHash, pageState, runHash, showError} from "./util.js";
import {pageWorkspace} from "./pages/workspace.js";
import {pageBacktest} from "./pages/backtest.js";
import {pageResearch} from "./pages/research.js";
import {pageLive} from "./pages/live.js";

async function route() {
  clearTimeout(pageState.pollTimer);
  document.body.classList.remove("wide");
  const [path, query] = location.hash.slice(1).split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  try {
    if (!TOKEN) throw new Error("Open the URL printed by `klean gui` (it includes the access token).");
    // addresses from klean <= 0.0.13 (bookmarks, links in reports) lead to the new dashboards
    if (parts[0] === "project") { location.replace(`#/backtest/${encodeURIComponent(parts[1])}`); return; }
    if (parts[0] === "run") { location.replace(runHash(parts.slice(1).join("/"))); return; }
    if (parts[0] === "optimization") { location.replace(optHash(parts[1], parts[2])); return; }
    if (parts[0] === "compare") {
      const refs = new URLSearchParams(query || "").getAll("ref");
      location.replace(refs.length ? compareHash(refs) : "#/"); return;
    }
    if (parts[0] === "backtest") await pageBacktest(parts[1], query);
    else if (parts[0] === "research") await pageResearch(parts[1] || "", query);
    else if (parts[0] === "live") await pageLive(parts[1], query);
    else await pageWorkspace();
    if (!document.getElementById("ws").textContent) api("/api/workspace").then(w => {
      document.getElementById("ws").textContent = w.root;
      document.getElementById("demobar").hidden = !(w.data || {}).synthetic_demo_data; }).catch(() => {});
  } catch (e) { showError(e); }
}
window.addEventListener("hashchange", route);
route();
