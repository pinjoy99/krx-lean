// Live dashboard for one project: paper trading in LEAN's live mode on daily KRX data
// (klean's LEAN plugin: one run per trading day, orders filled at the next day's open).
// Left: deploy, and the deployments. Right: the selected one's account, equity, positions,
// orders, fills and daily runs.
import {api, app, compact, day, esc, full, liveHash, setTitle, won} from "../util.js";
import {lineChart} from "../chart.js";

let shown = null;     // {project, data}

export async function pageLive(project, query) {
  setTitle(`Live · ${project}`);
  const left = document.getElementById("lv-left");
  if (!shown || shown.project !== project || !left || !document.body.contains(left)) await drawDashboard(project);
  await drawRight(new URLSearchParams(query || "").get("test") || shown.data.deployments[0]?.id || "");
}

async function drawDashboard(project) {
  const p = await api("/api/live", {project});
  shown = {project, data: p};
  app.innerHTML = `<div class="dashhead">
      <h1>${esc(p.name)} <span class="badge run">${esc(p.language)}</span></h1>
      <span class="muted">Live</span>
    </div>
    <div class="cols">
      <div id="lv-left" class="col-left"></div>
      <div id="lv-right" class="col-right"></div>
    </div>`;
  drawLeft();
}

function brokerBadge(d) {
  return d.broker === "kis-paper" || d.broker === "kis" ? '<span class="badge paper">KIS-PAPER</span>'
    : '<span class="badge paper">paper</span>';
}

// "2026-11-30T08:30:00+09:00" -> "Mon 2026-11-30 08:30 KST (Sun 18:30 here)"
function kst(iso) {
  const t = new Date(iso), days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const k = new Date(t.getTime() + 9 * 3600e3);       // KST wall clock, read in UTC
  const two = n => String(n).padStart(2, "0");
  return `${days[k.getUTCDay()]} ${k.toISOString().slice(0, 10)} ${two(k.getUTCHours())}:${two(k.getUTCMinutes())} KST` +
    ` (${days[t.getDay()]} ${two(t.getHours())}:${two(t.getMinutes())} here)`;
}

function stateBadge(d) {
  const cls = {running: "ok", stopped: "", failed: "no", "waiting for data": "run", "waiting for the pre-open run": "run"}[d.state]
    ?? (d.state.startsWith("missed") ? "no" : "");
  return `${brokerBadge(d)} <span class="badge ${cls}">${esc(d.state)}</span>${d.backdated ? ' <span class="badge demo">backdated</span>' : ""}`;
}

const pct = v => (v > 0 ? "+" : "") + v.toFixed(2) + "%";
const sign = v => v > 0 ? "pos" : v < 0 ? "neg" : "";

function drawLeft() {
  const p = shown.data, el = document.getElementById("lv-left");
  el.innerHTML = `
    <details class="panel" id="newlive" ${p.deployments.length ? "" : "open"}><summary><h2>New paper deployment</h2></summary>
      <p class="muted">Freezes ${esc(p.name)}'s code now and gives it a paper account. Each trading day (after
        <code>klean update data</code>) LEAN runs it in live mode: it sees that day's prices, places orders, and the
        orders fill at the next trading day's open with KRX fees, tax and slippage. No broker, no real money.</p>
      <label class="field">Broker
        <select id="lvbroker"><option value="paper">klean's paper broker (fills at the next open, from the KRX data)</option>
          <option value="kis-paper" ${p.kis.configured ? "" : "disabled"}>KIS-PAPER: a Korea Investment 모의투자 (paper) account${p.kis.configured ? "" : " (set KIS_* in ~/.config/krx-lean.env)"}</option>
        </select></label>
      <p class="muted small2" id="lvkisnote" style="display:none">KIS-PAPER: the 모의투자 account and its cash come from KIS; orders go out at the
        pre-open auction (08:30–08:59 KST) of each trading day, from the next one, using that day's prices from KIS.
        Schedule <code>klean live run</code> in that window.</p>
      <label class="field">Parameters from
        <select id="lvrun"><option value="">the code's defaults</option>
          ${p.runs.map(r => `<option value="${esc(r.ref)}">${esc(r.name)}${Object.keys(r.parameters).length ? " · " + esc(Object.entries(r.parameters).map(([k, v]) => k + "=" + v).join(", ")) : ""}</option>`).join("")}
        </select></label>
      <div class="grid2">
        <label class="field">Name (optional)<input type="text" id="lvname" placeholder="e.g. 30 holdings"></label>
        <label class="field">Starting cash (won)<input type="text" id="lvcash" value="100,000,000"></label>
      </div>
      <label class="field">First trading day (empty: the next one)<input type="text" id="lvstart" placeholder="after ${esc(p.data_last_date)}"></label>
      <p class="muted small2">A day on or before ${esc(p.data_last_date)} (the latest data) makes a <b>backdated</b>
        deployment, to try it on days the data already has; it's labeled so.</p>
      <div class="row"><button id="lvgo">Deploy</button><span id="lvstate" class="muted"></span></div>
    </details>
    <div class="panel"><h2>Deployments (${p.deployments.length})</h2>
      ${p.deployments.length ? `<table class="runs"><tr><th>Deployment</th><th>Days</th><th class="num">Net</th></tr>
        ${p.deployments.map(d => `<tr data-test="${esc(d.id)}"><td><a href="${liveHash(p.name, d.id)}">${esc(d.name)}</a><div>${stateBadge(d)}</div></td>
          <td>${esc(d.first_session)}<div class="muted small2">to ${esc(d.last_session && d.days ? d.last_session : "—")} · ${d.days} days</div></td>
          <td class="num ${sign(d.net_profit)}">${d.days ? pct(d.net_profit) : "—"}</td></tr>`).join("")}</table>`
        : '<p class="muted">None yet.</p>'}
    </div>`;
  const $ = id => document.getElementById(id);
  $("lvbroker").onchange = () => {
    const k = $("lvbroker").value === "kis-paper";
    $("lvkisnote").style.display = k ? "block" : "none";
    $("lvcash").closest("label").style.display = k ? "none" : "";
    $("lvstart").closest("label").style.display = k ? "none" : "";
  };
  $("lvgo").onclick = async () => {
    const btn = $("lvgo"), state = $("lvstate");
    btn.disabled = true; state.textContent = "deploying…";
    try {
      const job = await api("/api/live-deploy", {}, {project: p.name, run: $("lvrun").value, name: $("lvname").value.trim(),
                                                     cash: $("lvcash").value.trim(), start: $("lvstart").value.trim(),
                                                     broker: $("lvbroker").value});
      const j = await waitFor(job, state);
      shown.data = await api("/api/live", {project: p.name});
      drawLeft();
      location.hash = liveHash(p.name, job.deployment);
      if (j.note) document.getElementById("lvmsg")?.replaceChildren(j.note);
    } catch (e) { state.innerHTML = `<span class="err">${esc(e.message)}</span>`; btn.disabled = false; }
  };
}

// Poll a live job until it ends; shows progress in `state`.
async function waitFor(job, state) {
  for (;;) {
    const j = await api("/api/job", {id: job.id});
    if (j.status !== "running") {
      if (j.status === "failed") throw new Error(j.error.split("\n")[0]);
      return j;
    }
    const day = (j.console || []).filter(l => l.includes("trading day")).at(-1)?.split("trading day ")[1];
    state.innerHTML = `<span class="badge run">running</span> ${day ? "trading day " + esc(day) + ", " : ""}${Math.round(Date.now() / 1000 - j.started)} s`;
    await new Promise(r => setTimeout(r, 1500));
  }
}

function table(head, rows, empty) {
  return rows.length ? `<div class="scroll"><table class="runs"><tr>${head.map(h => `<th class="${h.startsWith("#") ? "num" : ""}">${esc(h.replace(/^#/, ""))}</th>`).join("")}</tr>${rows.join("")}</table></div>`
    : `<p class="muted">${empty}</p>`;
}

async function drawRight(id) {
  const el = document.getElementById("lv-right"), p = shown.data;
  document.querySelectorAll("#lv-left tr[data-test]").forEach(tr => tr.classList.toggle("sel", tr.dataset.test === id));
  if (!id) {
    el.innerHTML = `<div class="panel"><h2>No deployments yet</h2><p class="muted">Deploy one on the left. From the next
      trading day on, it trades every day after <code>klean update data</code>.</p></div>`;
    return;
  }
  el.innerHTML = '<p class="muted">Loading…</p>';
  let d;
  try { d = await api("/api/live-deployment", {project: p.name, id}); }
  catch (e) { el.innerHTML = `<div class="panel"><div class="err">${esc(e.message)}</div></div>`; return; }
  const params = Object.entries(d.parameters).map(([k, v]) => `${esc(k)}=${esc(v)}`).join(", ") || "the code's defaults";
  const tile = (k, v, cls = "") => `<div class="tile"><div class="k">${k}</div><div class="v ${cls}">${v}</div></div>`;
  const positions = d.positions.map(x => `<tr><td>${esc(x.symbol)}</td><td class="num">${full.format(x.quantity)}</td>
      <td class="num">${won(x.average_price)}</td><td class="num">${x.last != null ? won(x.last) : "—"}</td>
      <td class="num">${x.value != null ? won(x.value) : "—"}</td><td class="num ${sign(x.pnl)}">${x.pnl != null ? won(x.pnl) : "—"}</td>
      <td class="num">${x.weight.toFixed(1)}%</td></tr>`);
  const waiting = d.waiting.map(o => `<tr><td class="num">${o.id}</td><td>${esc(o.placed_session)}</td><td>${esc(o.symbol)}</td>
      <td>${esc(o.type)}</td><td class="num ${o.quantity < 0 ? "neg" : "pos"}">${full.format(o.quantity)}</td>
      <td class="num">${o.limit_price != null ? won(o.limit_price) : ""}</td><td class="muted">${esc(o.tag)}</td></tr>`);
  const fills = d.fills.map(f => `<tr><td>${esc(f.session)}</td><td class="num">${f.order_id}</td><td>${esc(f.symbol)}</td>
      <td class="num ${f.quantity < 0 ? "neg" : "pos"}">${full.format(f.quantity)}</td><td class="num">${won(f.price)}</td>
      <td class="num">${won(f.commission)}</td><td class="num">${won(f.tax)}</td><td>${esc(f.type)}</td></tr>`);
  const runs = d.runs.map(r => `<tr><td>${esc(r.session)}</td><td>${r.ok ? '<span class="badge ok">ok</span>' : '<span class="badge no">failed</span>'}</td>
      <td class="num">${r.equity != null ? won(r.equity) : ""}</td><td class="num">${r.orders ?? ""}</td><td class="num">${r.fills ?? ""}</td>
      <td class="num muted">${r.seconds ?? ""} s</td><td><a data-console="${esc(r.session)}">console</a>${r.error ? ` <span class="err">${esc(r.error)}</span>` : ""}</td></tr>`);
  const events = d.events.map(e => `<tr><td>${esc(e.session)}</td><td class="num">${e.order_id}</td><td>${esc(e.symbol)}</td><td>${esc(e.status)}</td><td>${esc(e.message)}</td></tr>`);
  el.innerHTML = `<div class="panel">
      <div class="row"><h2 class="runtitle" style="margin:0">${esc(d.name)}</h2> ${stateBadge(d)}
        <span class="spacer" style="flex:1"></span>
        ${d.status === "running" ? `<button class="secondary" id="lvrunbtn">${d.pending_days.length ? `Trade ${d.pending_days.length} new day(s)` : "Check for new days"}</button>
          <button class="secondary" id="lvstop">Stop</button>` : ""}</div>
      <p class="muted">${d.broker === "kis-paper" || d.broker === "kis" ? "KIS-PAPER (Korea Investment 모의투자) · orders at the pre-open auction (08:30–08:59 KST) · " : "Paper broker · "}trading from <b>${esc(d.first_session)}</b> with ${params}${d.source_run ? ` (from ${esc(d.source_run)})` : ""}.
        Code frozen ${esc(d.created_utc.slice(0, 10))}, starting cash ${won(d.start_cash)}.
        ${d.state === "waiting for data" ? `Waiting for the first trading day's data: <code>klean update data</code> runs it.` : ""}
        ${d.next_pre_open ? `Next pre-open run: <b>${esc(kst(d.next_pre_open))}</b>.` : ""}</p>
      ${d.missed_pre_opens?.length ? `<div class="failbox"><b>Missed ${d.missed_pre_opens.length} pre-open run(s)</b> (${esc(d.missed_pre_opens.join(", "))}): no
        <code>klean live run</code> ran in the 08:30–08:59 KST window, so nothing was traded those days.</div>` : ""}
      ${d.schedule_warning ? `<div class="failbox"><b>Not scheduled.</b> ${esc(d.schedule_warning)}</div>` : ""}
      <span id="lvmsg" class="muted"></span>
    </div>
    <div class="tiles">
      ${tile("Equity", won(d.equity))}${tile("Net profit", d.days ? pct(d.net_profit) : "—", sign(d.net_profit))}
      ${tile("Cash", d.cash != null ? won(d.cash) : "—")}${tile("Positions", d.positions.length)}
      ${tile("Waiting orders", d.waiting.length)}${tile("Trading days", `${d.days}${d.last_session && d.days ? `<div class="muted small2">to ${esc(d.last_session)}</div>` : ""}`)}
    </div>
    <div class="panel"><h2>Equity</h2><p class="muted small">At each day's close; KOSPI 200 scaled to the starting cash.</p><div id="lveq"></div></div>
    <div class="panel"><div class="tabs">
        <a data-t="pos" class="on">Positions (${d.positions.length})</a><a data-t="wait">Waiting orders (${d.waiting.length})</a>
        <a data-t="fills">Fills (${d.fills.length})</a><a data-t="runs">Daily runs (${d.runs.length})</a>${d.events.length ? `<a data-t="events">Notices (${d.events.length})</a>` : ""}</div>
      <div data-p="pos">${table(["Code", "#Shares", "#Average", "#Last close", "#Value", "#P&L", "#Weight"], positions, "No positions.")}</div>
      <div data-p="wait" style="display:none">${table(["#Order", "Placed on", "Code", "Type", "#Shares", "#Limit", "Tag"], waiting,
        "No waiting orders.")}<p class="muted small2">Orders placed on a trading day fill at the next trading day's open.</p></div>
      <div data-p="fills" style="display:none">${table(["Day", "#Order", "Code", "#Shares", "#Price", "#Commission", "#Tax", "Type"], fills, "No fills yet.")}</div>
      <div data-p="runs" style="display:none">${table(["Trading day", "", "#Equity", "#Orders", "#Fills", "#Time", ""], runs, "No runs yet.")}<pre id="lvconsole" style="display:none;margin-top:8px"></pre></div>
      <div data-p="events" style="display:none">${table(["Day", "#Order", "Code", "Status", "Why"], events, "")}</div>
    </div>`;
  if (d.equity_curve.length) {
    lineChart(document.getElementById("lveq"), [{label: "Account", points: d.equity_curve},
      {label: "KOSPI 200", points: d.benchmark, dashed: true}], {height: 240, yFmt: v => "₩" + compact.format(v),
       xFmt: t => day(t).slice(5), ...(d.equity_curve.length <= 20 ? {xTicks: d.equity_curve.map(p => p[0])} : {})});
  } else document.getElementById("lveq").innerHTML = '<p class="muted">No trading days yet.</p>';
  el.querySelectorAll(".tabs a").forEach(a => a.onclick = () => {
    el.querySelectorAll(".tabs a").forEach(x => x.classList.toggle("on", x === a));
    el.querySelectorAll("[data-p]").forEach(x => x.style.display = x.dataset.p === a.dataset.t ? "block" : "none");
  });
  el.querySelectorAll("a[data-console]").forEach(a => a.onclick = async () => {
    const c = await api("/api/live-console", {project: p.name, id, session: a.dataset.console});
    const pre = document.getElementById("lvconsole"); pre.style.display = "block"; pre.textContent = c.lines.join("\n");
  });
  const runBtn = document.getElementById("lvrunbtn");
  if (runBtn) {
    runBtn.onclick = async () => {
      runBtn.disabled = true;
      try {
        const j = await waitFor(await api("/api/live-run", {}, {project: p.name, id}), document.getElementById("lvmsg"));
        shown.data = await api("/api/live", {project: p.name}); drawLeft();
        await drawRight(id);
        if (j.note) document.getElementById("lvmsg").textContent = j.note;
      } catch (e) { document.getElementById("lvmsg").innerHTML = `<span class="err">${esc(e.message)}</span>`; runBtn.disabled = false; }
    };
    document.getElementById("lvstop").onclick = async () => {
      if (!confirm(`Stop ${d.name}? It won't trade on new days any more; its account and history stay.`)) return;
      const r = await api("/api/live-stop", {}, {project: p.name, id});
      shown.data = await api("/api/live", {project: p.name}); drawLeft();
      await drawRight(id);
      if (r.stopping) document.getElementById("lvmsg").textContent =
        "It's processing a trading day right now (started elsewhere): it stops when that day is done.";
    };
  }
}
