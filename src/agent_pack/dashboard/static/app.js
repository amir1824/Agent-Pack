"use strict";
(() => {
  // src/agent_pack/dashboard/ui/flow.ts
  function roleLabel(name) {
    return String(name).split(/[-_]/).filter(Boolean).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
  }
  function stepByName(run) {
    return Object.fromEntries((run.steps || []).map((step) => [step.name, step]));
  }
  function planPhase(name, index, activeIndex, nextIndex, byName) {
    const step = byName[name];
    if (step) {
      if (step.status === "done") return "done";
      if (step.status === "failed") return "failed";
      if (step.status === "started") return "active";
    }
    if (activeIndex >= 0) {
      return index === activeIndex + 1 ? "upcoming" : "waiting";
    }
    return index === nextIndex ? "upcoming" : "waiting";
  }
  function stepNode(step) {
    const phase = step.status === "started" ? "active" : step.status === "done" ? "done" : step.status === "failed" ? "failed" : "waiting";
    return {
      kind: "step",
      name: step.name,
      label: roleLabel(step.name),
      phase,
      status: step.status,
      at: step.at || "",
      detail: step.detail || "",
      log: step.log || []
    };
  }
  function plannedNodes(run, byName) {
    const plan = run.plan || [];
    if (!plan.length) {
      return (run.steps || []).map(stepNode);
    }
    const activeIndex = plan.findIndex((label) => byName[label]?.status === "started");
    const nextIndex = plan.findIndex((label) => byName[label]?.status !== "done");
    const nodes = plan.map((name, index) => {
      const step = byName[name];
      const phase = planPhase(name, index, activeIndex, nextIndex, byName);
      return {
        kind: "step",
        name,
        label: roleLabel(name),
        phase,
        status: step?.status || phase,
        at: step?.at || "",
        detail: step?.detail || "",
        log: step?.log || []
      };
    });
    const extras = (run.steps || []).filter((step) => !plan.includes(step.name)).map(stepNode);
    return [...nodes, ...extras];
  }
  function completeNode(run) {
    const OUTCOME_PHASE = { open: "pending", done: "done", failed: "failed", abandoned: "failed" };
    const endPhase = OUTCOME_PHASE[run.outcome] ?? "pending";
    return {
      kind: "complete",
      name: "complete",
      label: "Complete",
      phase: endPhase,
      status: endPhase,
      at: run.completed_at || "",
      detail: run.outcome,
      log: []
    };
  }
  function flowNodes(run) {
    const byName = stepByName(run);
    return [
      {
        kind: "start",
        name: "start",
        label: "Start",
        phase: "done",
        status: "done",
        at: run.started_at,
        detail: run.request_text || "",
        log: []
      },
      ...plannedNodes(run, byName),
      completeNode(run)
    ];
  }
  function flowProgress(run) {
    const plan = run.plan || [];
    const byName = stepByName(run);
    if (!plan.length) {
      const done2 = (run.steps || []).filter((step) => step.status === "done").length;
      const total = (run.steps || []).length;
      return { done: done2, total: total || 0, label: total ? `${done2}/${total}` : "\u2014" };
    }
    const done = plan.filter((name) => byName[name]?.status === "done").length;
    return { done, total: plan.length, label: `${done}/${plan.length}` };
  }
  function edgeClass(leftNode) {
    return leftNode.phase === "done" ? "edge solid" : "edge dashed";
  }
  function nodeIcon(phase) {
    if (phase === "done") return "\u2713";
    if (phase === "active") return "\u25CF";
    if (phase === "failed") return "\u2715";
    if (phase === "upcoming") return "\u25CB";
    return "\xB7";
  }
  function renderNode(run, node, index, escapeHtml2) {
    return `
    <button type="button" class="node ${escapeHtml2(node.phase)}" data-kind="${escapeHtml2(node.kind)}" data-run="${escapeHtml2(run.invocation_id)}" data-index="${index}">
      <span class="node-icon" aria-hidden="true">${nodeIcon(node.phase)}</span>
      <strong>${escapeHtml2(node.label || node.name)}</strong>
      <span>${escapeHtml2(node.phase)}</span>
    </button>`;
  }
  function renderFlow(run, escapeHtml2, chip2) {
    const nodes = flowNodes(run);
    const progress = flowProgress(run);
    const strip = nodes.map(
      (node, index) => `${index ? `<i class="${edgeClass(nodes[index - 1])}"></i>` : ""}${renderNode(run, node, index, escapeHtml2)}`
    ).join("");
    return `
    <article class="panel flow hero">
      <div class="flow-head">
        <div>
          <p class="kicker">Live flow</p>
          <h3>${escapeHtml2(run.profile_id)} \xB7 ${escapeHtml2(run.request_text || "open run")}</h3>
        </div>
        <div class="flow-meta">
          <span class="progress">${escapeHtml2(progress.label)}</span>
          ${chip2("open", "warn")}
        </div>
      </div>
      <div class="strip">${strip}</div>
    </article>`;
  }

  // src/agent_pack/dashboard/ui/log_rows.ts
  var LOG_PAGE_SIZE = 25;
  function renderLogTimeline(entries, escapeHtml2, chip2) {
    if (!entries.length) return '<p class="muted">No log entries yet.</p>';
    return `<ol class="log-timeline">${entries.map(
      (entry) => `
        <li class="log-entry ${escapeHtml2(entry.status || "pending")}">
          <time>${escapeHtml2(entry.at || "\u2014")}</time>
          ${chip2(entry.status || "pending", entry.status === "done" ? "ok" : entry.status === "failed" ? "bad" : "warn")}
          <p>${escapeHtml2(entry.detail || "\u2014")}</p>
        </li>`
    ).join("")}</ol>`;
  }
  function eventLogEntries(run, node) {
    if (node.kind === "start") {
      return (run.events || []).filter((event) => event.event === "started").map((event) => ({ status: "started", at: event.started_at ?? "", detail: event.request_text ?? "" }));
    }
    if (node.kind === "complete") {
      const completed = (run.events || []).find((event) => event.event === "completed");
      if (completed) return [{ status: completed.outcome ?? "completed", at: completed.completed_at ?? "", detail: `Run ${completed.outcome ?? "closed"}` }];
      return [{ status: "pending", at: "\u2014", detail: "Still running" }];
    }
    return node.log || [];
  }
  function runTimeline(run) {
    const eventRows = (run.events || []).map((event) => ({
      at: event.started_at ?? event.completed_at ?? "",
      kind: event.event ?? "",
      label: event.request_text ?? event.outcome ?? ""
    }));
    const stepRows = (run.steps || []).flatMap(
      (step) => (step.log || []).map((entry) => ({
        at: entry.at ?? "",
        kind: "step",
        label: `${step.name}: ${entry.status}${entry.detail ? ` \u2014 ${entry.detail}` : ""}`
      }))
    );
    return [...eventRows, ...stepRows].sort((left, right) => left.at.localeCompare(right.at));
  }
  function allLogRows(runs) {
    return runs.flatMap(
      (run) => runTimeline(run).map((row) => ({
        at: row.at,
        kind: row.kind,
        runId: run.invocation_id,
        profile: run.profile_id,
        detail: row.label
      }))
    ).sort((left, right) => right.at.localeCompare(left.at));
  }
  function clampLogPage(page, totalRows) {
    const maxPage = Math.max(0, Math.ceil(totalRows / LOG_PAGE_SIZE) - 1);
    return Math.min(Math.max(page, 0), maxPage);
  }

  // src/agent_pack/dashboard/ui/markdown.ts
  function escapeHtml(value) {
    return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
  }
  function inline(text) {
    return text.replaceAll(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replaceAll(/`([^`]+)`/g, "<code>$1</code>");
  }
  function renderMarkdown(src) {
    const escaped = escapeHtml(src || "");
    const blocks = escaped.split(/```(?:\w*)\n?/);
    const html = blocks.map((chunk, index) => {
      if (index % 2 === 1) {
        return `<pre><code>${chunk.replace(/\n$/, "")}</code></pre>`;
      }
      return chunk.split("\n").map((line) => {
        if (line.startsWith("### ")) return `<h3>${inline(line.slice(4))}</h3>`;
        if (line.startsWith("## ")) return `<h2>${inline(line.slice(3))}</h2>`;
        if (line.startsWith("# ")) return `<h1>${inline(line.slice(2))}</h1>`;
        if (line.startsWith("- ")) return `<li>${inline(line.slice(2))}</li>`;
        if (!line.trim()) return "";
        return `<p>${inline(line)}</p>`;
      }).join("\n").replaceAll(/(?:<li>.*<\/li>\n?)+/g, (list) => `<ul>${list}</ul>`);
    }).join("");
    return html || '<p class="muted">Empty file.</p>';
  }

  // src/agent_pack/dashboard/ui/views.ts
  var LANES = ["done", "failed", "abandoned"];
  function renderStats(data, statsEl) {
    const counts = data.counts;
    statsEl.innerHTML = ["skills", "profiles", "open", "done"].map((key) => `<div><dt>${key}</dt><dd>${counts[key] ?? 0}</dd></div>`).join("");
  }
  function chip(label, tone) {
    return `<span class="chip ${tone}">${escapeHtml(label)}</span>`;
  }
  function toneFor(stateLabel) {
    if (stateLabel === "clean" || stateLabel === "valid") return "ok";
    if (stateLabel === "dirty" || stateLabel === "not synced") return "warn";
    return "bad";
  }
  function renderOverview(data) {
    const pack = data.pack;
    const lock = data.lock;
    const errors = pack && pack.errors.length ? `<ul class="errors">${pack.errors.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : "";
    const projections = data.projections.length ? `<table class="table"><thead><tr><th>Host path</th><th>Source</th><th></th></tr></thead><tbody>${data.projections.map(
      (row) => `<tr><td>${escapeHtml(row.path)}</td><td>${escapeHtml(row.source)}</td><td>${row.present ? chip("present", "ok") : chip("missing", "bad")}</td></tr>`
    ).join("")}</tbody></table>` : '<p class="muted">No host projections in this checkout.</p>';
    const lockState = lock ? chip(lock.state, toneFor(lock.state)) : "";
    const valid = pack ? chip(pack.valid ? "valid" : "invalid", pack.valid ? "ok" : "bad") : "";
    return `
    <div class="grid">
      <article class="panel">
        <p class="kicker">Checkout</p>
        <p class="muted">${escapeHtml(pack && pack.description || "Consumer checkout")}</p>
        ${valid}${lockState}
        ${errors}
      </article>
      <article class="panel">
        <p class="kicker">Pin</p>
        <h3>${escapeHtml(lock ? `${lock.source}@${lock.tag}` : "source tree")}</h3>
        <p class="muted">${escapeHtml(lock ? lock.commit : data.root)}</p>
      </article>
    </div>
    <article class="panel stack">
      <p class="kicker">Projections</p>
      ${projections}
    </article>
  `;
  }
  function eventTone(kind) {
    if (kind === "completed" || kind === "done") return "ok";
    if (kind === "failed" || kind === "abandoned") return "bad";
    return "warn";
  }
  function renderLogTable(rows, page) {
    if (!rows.length) {
      return `<section class="log-panel panel">
      <div class="log-head"><p class="kicker">Log</p></div>
      <p class="empty">No run records yet.<br><code>pack record start --profile-id generic-agent --request "demo"</code></p>
    </section>`;
    }
    const total = rows.length;
    const pages = Math.max(1, Math.ceil(total / LOG_PAGE_SIZE));
    const safePage = Math.min(Math.max(page, 0), pages - 1);
    const start = safePage * LOG_PAGE_SIZE;
    const slice = rows.slice(start, start + LOG_PAGE_SIZE);
    const from = start + 1;
    const to = start + slice.length;
    const body = slice.map(
      (row) => `
      <tr>
        <td class="mono num">${escapeHtml(row.at || "\u2014")}</td>
        <td>${chip(row.kind, eventTone(row.kind))}</td>
        <td class="mono"><span class="run-id">${escapeHtml(row.runId.slice(0, 12))}</span> <span class="muted">${escapeHtml(row.profile)}</span></td>
        <td>${escapeHtml(row.detail)}</td>
      </tr>`
    ).join("");
    return `<section class="log-panel panel">
    <div class="log-head">
      <p class="kicker">Log</p>
      <div class="pager">
        <span class="pager-meta">Showing ${from}\u2013${to} of ${total}</span>
        <button type="button" class="ghost" data-log-page="${safePage - 1}" ${safePage <= 0 ? "disabled" : ""}>Prev</button>
        <button type="button" class="ghost" data-log-page="${safePage + 1}" ${safePage >= pages - 1 ? "disabled" : ""}>Next</button>
      </div>
    </div>
    <div class="log-scroll">
      <table class="log-table">
        <thead><tr><th>Time</th><th>Event</th><th>Run</th><th>Detail</th></tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  </section>`;
  }
  function renderRuns(data, logPage) {
    const live = (data.runs || []).filter((run) => run.outcome === "open").map((run) => renderFlow(run, escapeHtml, chip)).join("");
    const lanes = LANES.map((lane) => {
      const cards = data.runs.filter((run) => run.outcome === lane).map(
        (run) => `
          <button type="button" class="run" data-kind="run" data-id="${escapeHtml(run.invocation_id)}">
            <strong>${escapeHtml(run.profile_id)}</strong>
            ${escapeHtml(run.request_text || "\u2014")}
            <span class="mono num">${escapeHtml(run.started_at)}</span>
            ${run.pack_tag ? chip(run.pack_tag, "ok") : ""}
          </button>`
      ).join("") || '<p class="muted">None</p>';
      return `<section class="lane ${lane}"><h3>${lane}<span class="num">${data.counts[lane]}</span></h3>${cards}</section>`;
    }).join("");
    const rows = allLogRows(data.runs || []);
    return `${live}<div class="board">${lanes}</div>${renderLogTable(rows, logPage)}`;
  }
  function renderCards(items, kind) {
    if (!items.length) {
      return `<p class="empty">No ${kind} in this checkout.</p>`;
    }
    return `<div class="grid">${items.map(
      (item) => `
        <button type="button" class="card" data-kind="${kind}" data-id="${escapeHtml(item.id)}">
          <p class="kicker">${escapeHtml(kind)}</p>
          <h3>${escapeHtml(item.name || item.id)}</h3>
          ${item.description ? `<p class="muted">${escapeHtml(item.description)}</p>` : ""}
        </button>`
    ).join("")}</div>`;
  }

  // src/agent_pack/dashboard/ui/app.ts
  var state = {
    view: "overview",
    data: null,
    fingerprint: "",
    selected: null,
    logPage: 0
  };
  var $ = (id) => {
    const el = document.getElementById(id);
    if (!el) {
      throw new Error(`missing #${id}`);
    }
    return el;
  };
  var POLL_ACTIVE_MS = 1e3;
  var POLL_IDLE_MS = 2e3;
  function renderConstitution(data) {
    return `<article class="panel prose">${renderMarkdown(data.constitution)}</article>`;
  }
  var views = {
    overview: (data) => renderOverview(data),
    runs: (data) => renderRuns(data, state.logPage),
    skills: (data) => renderCards(data.skills, "skill"),
    profiles: (data) => renderCards(data.profiles, "profile"),
    constitution: renderConstitution
  };
  function viewLabel() {
    return document.querySelector(`.nav [data-view="${state.view}"]`)?.textContent?.trim() || state.view;
  }
  function fillDrawer(runId, index) {
    const data = state.data;
    if (!data) {
      return false;
    }
    const run = data.runs.find((row) => row.invocation_id === runId);
    const node = run && flowNodes(run)[index];
    if (!node) {
      return false;
    }
    $("drawer-kicker").textContent = node.phase || node.kind;
    $("drawer-title").textContent = node.label || node.name;
    const skill = node.kind === "step" ? data.skills.find((row) => row.id === node.name) : null;
    const timeline = renderLogTimeline(eventLogEntries(run, node), escapeHtml, chip);
    const skillBlock = skill ? `<section class="skill-note"><p class="kicker">Skill</p>${renderMarkdown(skill.description)}</section>` : "";
    $("drawer-body").innerHTML = `${timeline}${skillBlock}`;
    return true;
  }
  function snapshotFingerprint(data) {
    return JSON.stringify({ runs: data.runs, counts: data.counts });
  }
  function paint() {
    const data = state.data;
    if (!data) {
      return;
    }
    const drawer = $("drawer");
    const keepOpen = Boolean(state.selected) && !drawer.hidden;
    const scrollTop = keepOpen ? $("drawer-body").scrollTop : 0;
    const label = viewLabel();
    $("view-title").textContent = label;
    $("kind-label").textContent = data.kind;
    $("root-path").textContent = data.root;
    const lock = data.lock;
    $("pin").textContent = lock ? `${lock.source}@${lock.tag}` : data.root;
    document.title = `${label} \xB7 agent-pack`;
    renderStats(data, $("stats"));
    $("view").innerHTML = views[state.view](data);
    if (state.selected && fillDrawer(state.selected.runId, state.selected.index)) {
      drawer.hidden = false;
      if (keepOpen) {
        $("drawer-body").scrollTop = scrollTop;
      }
    }
  }
  function renderRunBody(id) {
    const run = state.data?.runs.find((row) => row.invocation_id === id);
    if (!run) return "";
    const steps = (run.steps || []).map((step) => `- ${step.name}: ${step.status}`).join("\n");
    const pin = run.pack_tag ? `pack: ${run.pack_name ?? "\u2014"}@${run.pack_tag}
commit: ${run.pack_commit ?? "\u2014"}
` : "";
    return `${pin}profile: ${run.profile_id}
request: ${run.request_text}
started: ${run.started_at}
completed: ${run.completed_at || "\u2014"}
outcome: ${run.outcome}
${steps ? `
steps:
${steps}` : ""}`;
  }
  function openItemDrawer(kind, id) {
    const data = state.data;
    if (!data) return;
    state.selected = null;
    const skill = kind === "skill" ? data.skills.find((row) => row.id === id) : null;
    const profile = kind === "profile" ? data.profiles.find((row) => row.id === id) : null;
    const run = kind === "run" ? data.runs.find((row) => row.invocation_id === id) : null;
    $("drawer-kicker").textContent = skill?.path || run?.outcome || kind;
    $("drawer-title").textContent = skill?.name || profile?.name || run?.profile_id || id;
    const body = skill?.body || profile?.body || (run ? renderRunBody(id) : "");
    $("drawer-body").innerHTML = renderMarkdown(body);
    $("drawer").hidden = false;
  }
  function openNodeDrawer(runId, index) {
    state.selected = { runId, index };
    fillDrawer(runId, index);
    $("drawer").hidden = false;
  }
  function openDrawerFromElement(button) {
    const kind = button.dataset.kind || "";
    if (kind === "start" || kind === "complete" || kind === "step") {
      openNodeDrawer(String(button.dataset.run), Number(button.dataset.index));
      return;
    }
    openItemDrawer(kind, String(button.dataset.id));
  }
  async function load() {
    try {
      const resp = await fetch("/api/snapshot");
      if (!resp.ok) {
        throw new Error("snapshot failed");
      }
      const next = await resp.json();
      state.data = next;
      $("live").classList.remove("is-stale");
      const fingerprint = snapshotFingerprint(next);
      const rowCount = allLogRows(next.runs || []).length;
      state.logPage = clampLogPage(state.logPage, rowCount);
      if (fingerprint !== state.fingerprint) {
        state.fingerprint = fingerprint;
        paint();
      }
    } catch {
      $("live").classList.add("is-stale");
    }
  }
  async function tick() {
    await load();
    const open = Boolean(state.data?.runs?.some((run) => run.outcome === "open"));
    setTimeout(tick, open ? POLL_ACTIVE_MS : POLL_IDLE_MS);
  }
  function boot() {
    document.querySelector(".nav")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-view]");
      if (!button) {
        return;
      }
      state.view = button.dataset.view || "overview";
      document.querySelectorAll(".nav button").forEach((node) => node.classList.toggle("is-active", node === button));
      paint();
    });
    $("view").addEventListener("click", (event) => {
      const target = event.target;
      const pageBtn = target.closest("[data-log-page]");
      if (pageBtn && !pageBtn.hasAttribute("disabled")) {
        state.logPage = Number(pageBtn.dataset.logPage);
        paint();
        return;
      }
      const button = target.closest("[data-kind]");
      if (!button) {
        return;
      }
      openDrawerFromElement(button);
    });
    $("drawer-close").addEventListener("click", () => {
      state.selected = null;
      $("drawer").hidden = true;
    });
    void tick();
  }
  if (typeof document !== "undefined" && document.getElementById("view")) {
    boot();
  }
})();
