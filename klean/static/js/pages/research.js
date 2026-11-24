// Research: the workspace's JupyterLab inside the page. LEAN's QuantBook is loaded in every
// notebook; a project's notebook runs in the project folder (its krx_models etc. import).
// Each project opens in its own JupyterLab layout (open files, tabs, splits), kept in the
// project as .jupyter/layout.json: the strategy file and research.ipynb side by side at first.
// The project is chosen in the top bar; without one, JupyterLab shows the whole workspace.
import {api, app, esc, pageState, setTitle} from "../util.js";

const STATUS = {
  installing: "Installing JupyterLab into the workspace's Python environment (first time only, a few minutes)…",
  starting: "Starting JupyterLab…",
};

export async function pageResearch(project) {
  setTitle(project ? `Research · ${project}` : "Research");
  document.body.classList.add("wide");
  const w = await api("/api/workspace");
  const lang = w.projects.find(p => p.name === project)?.language;
  app.innerHTML = `<div class="research">
    <div class="dashhead researchbar">
      <h1>${project ? esc(project) + (lang ? ` <span class="badge run">${esc(lang)}</span>` : "") : "All files"}</h1>
      <span class="muted">Research</span>
      <span id="rstate" class="muted"></span>
      <span class="spacer"></span>
      ${project ? `<span id="rkernels" class="muted small"></span>
      <button class="secondary" id="rkill" title="Stop the kernels of this project's notebooks (frees their memory; variables are lost)" hidden>Shut down kernels</button>
      <button class="secondary" id="rreset" title="Close everything and show the strategy file and research.ipynb side by side again" hidden>Reset layout</button>` : ""}
      <a id="rtab" target="_blank" rel="noopener noreferrer" hidden>Open in a new tab</a>
    </div>
    <div id="rbody"><p class="muted">LEAN's QuantBook on this workspace's data, in JupyterLab. Notebooks, code files and a
      terminal: everything in the workspace folder. JupyterLab keeps running while klean gui runs.</p></div>
  </div>`;

  const state = document.getElementById("rstate"), body = document.getElementById("rbody");
  const show = url => {
    const tab = document.getElementById("rtab");
    tab.href = url; tab.hidden = false;
    body.innerHTML = `<iframe class="lab" title="JupyterLab" src="${esc(url)}"></iframe>`;
  };
  const kernels = n => {
    const el = document.getElementById("rkernels");
    if (!el || n === null || n === undefined) return;
    el.textContent = n === 1 ? "1 kernel running" : `${n} kernels running`;
    document.getElementById("rkill").disabled = n === 0;
  };
  const poll = async () => {
    if (!document.body.contains(state)) return;        // left the page
    let r;
    try { r = await api("/api/research", {}, project ? {project} : {}); }
    catch (e) { state.innerHTML = `<span class="err">${esc(e.message)}</span>`; return; }
    if (r.status === "ready") {
      state.innerHTML = '<span class="badge ok">running</span>';
      show(r.url);
      if (project) {
        document.getElementById("rkill").hidden = document.getElementById("rreset").hidden = false;
        kernels(r.kernels);
        wireProject();
        const refresh = async () => {                    // notebooks start and stop kernels inside JupyterLab
          if (!document.body.contains(state)) return;
          try { kernels((await api("/api/research", {}, {project})).kernels); } catch { /* shown on the next action */ }
          pageState.pollTimer = setTimeout(refresh, 15000);
        };
        pageState.pollTimer = setTimeout(refresh, 15000);
      }
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

  function wireProject() {
    document.getElementById("rreset").onclick = async () => {
      if (!confirm(`Reset ${project}'s layout? Open files close (they are saved files, nothing is lost) and the strategy and research.ipynb open side by side.`)) return;
      body.innerHTML = '<p class="muted">Resetting the layout…</p>';    // unload JupyterLab first, so it doesn't save the old layout over the new one
      try { show((await api("/api/research-layout", {}, {project, action: "reset"})).url); }
      catch (e) { body.innerHTML = `<p class="err">${esc(e.message)}</p>`; }
    };
    document.getElementById("rkill").onclick = async () => {
      if (!confirm(`Shut down the kernels of ${project}'s notebooks? Their variables are lost; run the cells again to get them back.`)) return;
      try {
        const r = await api("/api/research-layout", {}, {project, action: "shutdown"});
        kernels(0);
        state.innerHTML = `<span class="badge ok">running</span> <span class="muted">${r.stopped} kernel(s) shut down</span>`;
      } catch (e) { state.innerHTML = `<span class="err">${esc(e.message)}</span>`; }
    };
  }
  poll();
}
