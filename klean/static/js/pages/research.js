// Research: the workspace's JupyterLab inside the page. LEAN's QuantBook is loaded in every
// notebook; a project's notebook runs in the project folder (its krx_models etc. import).
// Each project opens in its own JupyterLab layout (open files, tabs, splits), kept in the
// project as .jupyter/layout.json: the strategy file and research.ipynb side by side at first.
// The project is chosen in the top bar; without one, JupyterLab shows the whole workspace.
// One browser tab at a time shows a project's Research: opening it in another tab (or with *Open in
// a new tab*) unloads it here first ("open in another tab — Use it here"), so there is one editor per
// file and the project keeps its own layout (JupyterLab gives a second window a new, empty one).
import {api, app, esc, pageState, setTitle} from "../util.js";

// Tabs of this klean page talk over a BroadcastChannel (same origin, no server involved).
const TAB = Math.random().toString(36).slice(2);
const channel = typeof BroadcastChannel === "function" ? new BroadcastChannel("klean-research") : null;
let holder = null;                 // {key, release(why)}: the Research this tab shows
const sleep = ms => new Promise(r => setTimeout(r, ms));
const waiting = new Map();         // claim id -> {releasing, released} (resolvers)
if (channel) channel.onmessage = async e => {
  const m = e.data || {};
  if (m.type === "claim" && m.tab !== TAB && holder && holder.key === m.key) {
    channel.postMessage({type: "releasing", id: m.id});
    await holder.release(m.tab === "standalone" ? "standalone" : "tab");
    channel.postMessage({type: "released", id: m.id});
  }
  const w = waiting.get(m.id);
  if (w && m.type === "releasing") w.releasing();
  if (w && m.type === "released") w.released();
};

// Take a project's Research for this tab. A tab showing it answers "releasing", saves (its
// editors lose focus: the autosave extension), unloads its JupyterLab and answers "released";
// only then does JupyterLab load here, and find the project's layout free.
async function claim(key, tab = TAB) {
  if (!channel) return;
  const id = `${TAB}-${Date.now()}-${Math.random()}`;
  let releasing, released;
  const gotReleasing = new Promise(r => { releasing = r; }), gotReleased = new Promise(r => { released = r; });
  waiting.set(id, {releasing, released});
  channel.postMessage({type: "claim", key, tab, id});
  if (await Promise.race([gotReleasing.then(() => true), sleep(400).then(() => false)]))
    await Promise.race([gotReleased, sleep(8000)]);               // someone had it: wait until it let go
  waiting.delete(id);
}

// Save what JupyterLab has open, by moving focus out of it (autosave-on-focus-change), and give the
// saves a moment to reach the server.
async function saveByLeaving(frame) {
  if (!frame) return;
  frame.blur();
  window.focus();
  await sleep(1500);
}

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
  const key = project || "*";              // "*": all files, the workspace-wide JupyterLab
  let generation = 0;                       // a newer show or release ends the older kernel refresh
  holder = null;
  const release = async why => {            // another tab (or JupyterLab's own tab) has it now
    if (!document.body.contains(body)) { holder = null; return; }      // left this page meanwhile
    generation++;
    holder = null;
    await saveByLeaving(body.querySelector("iframe.lab"));
    document.getElementById("rtab").hidden = true;
    for (const id of ["rkill", "rreset"]) { const b = document.getElementById(id); if (b) b.hidden = true; }
    const where = why === "standalone" ? "in its own browser tab (JupyterLab)" : "in another klean tab";
    state.innerHTML = '<span class="badge">elsewhere</span>';
    body.innerHTML = `<div class="panel lab-elsewhere"><h2>${esc(project || "All files")}: Research is open ${where}</h2>
      <p class="muted">One tab at a time edits a project's files, so they never overwrite each other. Your edits
        there are saved as you go.</p>
      <button id="rhere">Use it here</button></div>`;
    document.getElementById("rhere").onclick = () => { body.innerHTML = '<p class="muted">Opening…</p>'; poll(); };
  };
  const show = async url => {
    await claim(key);
    if (!document.body.contains(body)) return;
    generation++;
    holder = {key, release};
    const tab = document.getElementById("rtab");
    tab.href = url; tab.hidden = false;
    tab.onclick = async e => {                 // JupyterLab on its own: save and unload here first, then open it
      e.preventDefault();
      await claim(key, "standalone");          // other klean tabs showing it let go
      await release("standalone");
      window.open(url, "_blank", "noopener");
    };
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
      await show(r.url);
      if (!holder) return;                        // gone meanwhile (another tab claimed it)
      if (project) {
        document.getElementById("rkill").hidden = document.getElementById("rreset").hidden = false;
        kernels(r.kernels);
        wireProject();
        const mine = generation;
        const refresh = async () => {                    // notebooks start and stop kernels inside JupyterLab
          if (!document.body.contains(state) || generation !== mine) return;
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
