// klean GUI: hash router. Dashboards: #/ (workspace), #/research/P, #/backtest/P[?run=|?opt=|?cmp=…], #/live/P. Pages live in ./pages/, one module each.
// The top bar is the same on every dashboard: Workspace, the project, and its Research | Backtest | Live.
import {TOKEN, api, compareHash, esc, href, optHash, pageState, runHash, showError} from "./util.js";
import {pageWorkspace} from "./pages/workspace.js";
import {pageBacktest} from "./pages/backtest.js";
import {leaveResearch, pageResearch} from "./pages/research.js";
import {pageLive} from "./pages/live.js";

const LAST = "klean-last-project";
const nav = {projects: null, dash: "", project: ""};
const remember = name => { try { localStorage.setItem(LAST, name); } catch { /* private window: no memory */ } };
const recalled = () => { try { return localStorage.getItem(LAST) || ""; } catch { return ""; } };

async function workspaceInfo() {
  const w = await api("/api/projects");          // quick: names only, no setup check
  nav.projects = w.projects;
  document.getElementById("ws").textContent = w.root;
  document.getElementById("demobar").hidden = !w.demo;
}

// The top bar for dashboard `dash` ("" = Workspace) of `project`: the project list, the current
// project (the last one used on the Workspace page), and its dashboards as tabs.
async function drawNav(dash, project) {
  if (!nav.projects || (project && !nav.projects.includes(project))) await workspaceInfo();
  if (project) remember(project);
  const current = project || (dash ? "" : (nav.projects.includes(recalled()) ? recalled() : ""));
  const select = document.getElementById("nav-project");
  const first = dash === "research" && !project ? "All files" : "Project…";
  select.innerHTML = `<option value="">${first}</option>` + nav.projects.map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  select.value = current;
  select.onchange = () => {
    if (select.value) location.hash = href(dash || "research", select.value);
    else if (dash === "research") location.hash = "#/research";
  };
  document.getElementById("nav-ws").classList.toggle("on", dash === "");
  const tabs = document.getElementById("nav-tabs");
  tabs.hidden = !current;
  for (const a of tabs.querySelectorAll("a")) {
    a.href = current ? href(a.dataset.d, current) : "#/";
    a.classList.toggle("on", a.dataset.d === dash && !!project);
  }
}

async function route() {
  clearTimeout(pageState.pollTimer);
  document.body.classList.remove("wide");
  const [path, query] = location.hash.slice(1).split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  const dash = ["research", "backtest", "live"].includes(parts[0]) ? parts[0] : "";
  const project = dash ? parts[1] || "" : "";
  // leaving Research: let JupyterLab finish saving open files, then save the project's layout
  // into the project (also done every minute)
  if (nav.dash === "research" && (dash !== "research" || project !== nav.project)) {
    await leaveResearch();
    if (nav.project) api("/api/research-layout", {}, {project: nav.project, action: "save"}).catch(() => {});
  }
  nav.dash = dash; nav.project = project;
  try {
    if (!TOKEN) throw new Error("Open the URL printed by `klean gui` (it includes the access token).");
    if (dash === "") nav.projects = null;           // the Workspace page may list a new project
    const navDrawn = drawNav(dash, project).catch(() => {});      // the top bar and the page load side by side
    // addresses from klean <= 0.0.13 (bookmarks, links in reports) lead to the new dashboards
    if (parts[0] === "project") { location.replace(`#/backtest/${encodeURIComponent(parts[1])}`); return; }
    if (parts[0] === "run") { location.replace(runHash(parts.slice(1).join("/"))); return; }
    if (parts[0] === "optimization") { location.replace(optHash(parts[1], parts[2])); return; }
    if (parts[0] === "compare") {
      const refs = new URLSearchParams(query || "").getAll("ref");
      location.replace(refs.length ? compareHash(refs) : "#/"); return;
    }
    if (parts[0] === "backtest") await pageBacktest(parts[1], query);
    else if (parts[0] === "research") await pageResearch(parts[1] || "");
    else if (parts[0] === "live") await pageLive(parts[1], query);
    else await pageWorkspace();
    await navDrawn;
  } catch (e) { showError(e); }
}
window.addEventListener("hashchange", route);
route();
