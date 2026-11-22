// klean GUI: hash router (#/, #/project/P, #/run/P/…, #/optimization/P/O, #/compare?ref=…, #/research[/P]). Pages live in ./pages/, one module each.
import {TOKEN, api, pageState, showError} from "./util.js";
import {pageWorkspace} from "./pages/workspace.js";
import {pageProject} from "./pages/project.js";
import {pageRun} from "./pages/run.js";
import {pageOptimization} from "./pages/optimization.js";
import {pageCompare} from "./pages/compare.js";
import {pageResearch} from "./pages/research.js";

async function route() {
  clearTimeout(pageState.pollTimer);
  document.body.classList.remove("wide");
  const [path, query] = location.hash.slice(1).split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  try {
    if (!TOKEN) throw new Error("Open the URL printed by `klean gui` (it includes the access token).");
    if (parts[0] === "project") await pageProject(parts[1]);
    else if (parts[0] === "run") await pageRun(parts.slice(1).join("/"));
    else if (parts[0] === "optimization") await pageOptimization(parts[1], parts[2]);
    else if (parts[0] === "research") await pageResearch(parts[1] || "");
    else if (parts[0] === "compare") await pageCompare(new URLSearchParams(query || "").getAll("ref"));
    else await pageWorkspace();
    if (!document.getElementById("ws").textContent) api("/api/workspace").then(w => {
      document.getElementById("ws").textContent = w.root;
      document.getElementById("demobar").hidden = !(w.data || {}).synthetic_demo_data; }).catch(() => {});
  } catch (e) { showError(e); }
}
window.addEventListener("hashchange", route);
route();
