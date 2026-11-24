// Research: the workspace's JupyterLab inside the page. LEAN's QuantBook is loaded in every
// notebook; a project's notebook runs in the project folder (its krx_models etc. import).
// ?open=new (after New project): the strategy file and research.ipynb side by side.
import {api, app, backtestHash, esc, href, liveHash, pageState, setTitle} from "../util.js";

const STATUS = {
  installing: "Installing JupyterLab into the workspace's Python environment (first time only, a few minutes)…",
  starting: "Starting JupyterLab…",
};

export async function pageResearch(project, query = "") {
  const layout = project && new URLSearchParams(query || "").get("open") === "new" ? "new" : "";
  setTitle(project ? `Research · ${project}` : "Research");
  document.body.classList.add("wide");
  const w = await api("/api/workspace");
  const names = w.projects.map(p => p.name);
  const lang = w.projects.find(p => p.name === project)?.language;
  app.innerHTML = `<div class="research">
    <div class="dashhead researchbar">
      <a href="#/" class="back">‹ Workspace</a>
      <h1>${project ? esc(project) + (lang ? ` <span class="badge run">${esc(lang)}</span>` : "") : "Research"}</h1>
      <span class="muted">Research</span>
      <select id="rproj" aria-label="Notebook">
        <option value="">Workspace (all projects)</option>
        ${names.map(n => `<option value="${esc(n)}" ${n === project ? "selected" : ""}>${esc(n)} / research.ipynb</option>`).join("")}
      </select>
      <span id="rstate" class="muted"></span>
      <span class="spacer"></span>
      <a id="rtab" target="_blank" rel="noopener noreferrer" hidden>Open in a new tab</a>
      ${project ? `<a class="button" href="${backtestHash(project)}">Backtest</a>
      <a class="button secondary" href="${liveHash(project)}">Live</a>` : ""}
    </div>
    <div id="rbody"><p class="muted">LEAN's QuantBook on this workspace's data, in JupyterLab. Notebooks, code files and a
      terminal: everything in the workspace folder. JupyterLab keeps running while klean gui runs.</p></div>
  </div>`;
  document.getElementById("rproj").onchange = e => location.hash = e.target.value ? href("research", e.target.value) : "#/research";

  const state = document.getElementById("rstate"), body = document.getElementById("rbody");
  const poll = async () => {
    if (!document.body.contains(state)) return;        // left the page
    let r;
    try { r = await api("/api/research", {}, project ? {project, ...(layout ? {layout} : {})} : {}); }
    catch (e) { state.innerHTML = `<span class="err">${esc(e.message)}</span>`; return; }
    if (r.status === "ready") {
      state.innerHTML = '<span class="badge ok">running</span>';
      const tab = document.getElementById("rtab");
      tab.href = r.url; tab.hidden = false;
      body.innerHTML = `<iframe class="lab" title="JupyterLab" src="${esc(r.url)}"></iframe>`;
      return;
    }
    if (r.status === "failed" || r.status === "stopped") {
      state.innerHTML = `<span class="badge no">${esc(r.status)}</span>`;
      body.innerHTML = `<div class="failbox"><pre class="err">${esc(r.error)}</pre>
        <button id="rretry">Start again</button></div>`;
      document.getElementById("rretry").onclick = poll;
      return;
    }
    const secs = r.started ? Math.round(Date.now() / 1000 - r.started) : 0;
    state.innerHTML = `<span class="badge run">${esc(r.status)}</span> ${secs} s`;
    body.innerHTML = `<p class="muted">${esc(STATUS[r.status] || "")}</p>`;
    pageState.pollTimer = setTimeout(poll, 1000);
  };
  poll();
}
