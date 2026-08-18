const LANES = ["open", "done", "failed", "abandoned"];
const state = { view: "overview", data: null, selected: null };

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderMarkdown(src) {
  const escaped = escapeHtml(src || "");
  const blocks = escaped.split(/```(?:\w*)\n?/);
  const html = blocks
    .map((chunk, index) => {
      if (index % 2 === 1) {
        return `<pre><code>${chunk.replace(/\n$/, "")}</code></pre>`;
      }
      return chunk
        .split("\n")
        .map((line) => {
          if (line.startsWith("### ")) return `<h3>${inline(line.slice(4))}</h3>`;
          if (line.startsWith("## ")) return `<h2>${inline(line.slice(3))}</h2>`;
          if (line.startsWith("# ")) return `<h1>${inline(line.slice(2))}</h1>`;
          if (line.startsWith("- ")) return `<li>${inline(line.slice(2))}</li>`;
          if (!line.trim()) return "";
          return `<p>${inline(line)}</p>`;
        })
        .join("\n")
        .replaceAll(/(?:<li>.*<\/li>\n?)+/g, (list) => `<ul>${list}</ul>`);
    })
    .join("");
  return html || "<p class=\"muted\">Empty file.</p>";
}

function inline(text) {
  return text
    .replaceAll(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replaceAll(/`([^`]+)`/g, "<code>$1</code>");
}

function chip(label, tone) {
  return `<span class="chip ${tone}">${escapeHtml(label)}</span>`;
}

function toneFor(stateLabel) {
  if (stateLabel === "clean" || stateLabel === "valid") return "ok";
  if (stateLabel === "dirty" || stateLabel === "not synced") return "warn";
  return "bad";
}

function renderStats(data) {
  const counts = data.counts;
  $("stats").innerHTML = ["skills", "profiles", "open", "done"]
    .map(
      (key) =>
        `<div><dt>${key}</dt><dd>${counts[key] ?? 0}</dd></div>`,
    )
    .join("");
}

function renderOverview(data) {
  const pack = data.pack;
  const lock = data.lock;
  const errors = pack && pack.errors.length
    ? `<ul class="errors">${pack.errors.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : "";
  const projections = data.projections.length
    ? `<table class="table"><thead><tr><th>Host path</th><th>Source</th><th></th></tr></thead><tbody>${data.projections
        .map(
          (row) =>
            `<tr><td>${escapeHtml(row.path)}</td><td>${escapeHtml(row.source)}</td><td>${row.present ? chip("present", "ok") : chip("missing", "bad")}</td></tr>`,
        )
        .join("")}</tbody></table>`
    : "<p class=\"muted\">No host projections in this checkout.</p>";
  const lockState = lock ? chip(lock.state, toneFor(lock.state)) : "";
  const valid = pack ? chip(pack.valid ? "valid" : "invalid", pack.valid ? "ok" : "bad") : "";
  return `
    <div class="grid">
      <article class="panel">
        <p class="kicker">Pack</p>
        <h3>${escapeHtml(data.name)}</h3>
        <p class="muted">${escapeHtml((pack && pack.description) || "Consumer checkout")}</p>
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

function renderRuns(data) {
  const lanes = LANES.map((lane) => {
    const cards = data.runs
      .filter((run) => run.outcome === lane)
      .map(
        (run) => `
          <button type="button" class="run" data-kind="run" data-id="${escapeHtml(run.invocation_id)}">
            <strong>${escapeHtml(run.profile_id)}</strong>
            ${escapeHtml(run.request_text || "—")}
            <span>${escapeHtml(run.started_at)}</span>
          </button>`,
      )
      .join("") || `<p class="muted">None</p>`;
    return `<section class="lane ${lane}"><h3>${lane}<span>${data.counts[lane]}</span></h3>${cards}</section>`;
  }).join("");
  const events = data.runs.length
    ? data.runs
        .map(
          (run) =>
            `<div class="event"><span>${escapeHtml(run.started_at)}</span><span>${escapeHtml(run.outcome)}</span><span>${escapeHtml(run.profile_id)} · ${escapeHtml(run.request_text || "")}</span></div>`,
        )
        .join("")
    : `<p class="empty">No run records. Consumers write JSONL under .agents/log/ with pack record.</p>`;
  return `<div class="board">${lanes}</div><section class="timeline"><p class="kicker">Timeline</p>${events}</section>`;
}

function renderCards(items, kind) {
  if (!items.length) {
    return `<p class="empty">No ${kind} in this checkout.</p>`;
  }
  return `<div class="grid">${items
    .map(
      (item) => `
        <button type="button" class="card" data-kind="${kind}" data-id="${escapeHtml(item.id)}">
          <p class="kicker">${escapeHtml(item.path)}</p>
          <h3>${escapeHtml(item.name || item.id)}</h3>
          <p class="muted">${escapeHtml(item.description || "")}</p>
        </button>`,
    )
    .join("")}</div>`;
}

function renderConstitution(data) {
  return `<article class="panel prose">${renderMarkdown(data.constitution)}</article>`;
}

const views = {
  overview: renderOverview,
  runs: renderRuns,
  skills: (data) => renderCards(data.skills, "skill"),
  profiles: (data) => renderCards(data.profiles, "profile"),
  constitution: renderConstitution,
};

function paint() {
  const data = state.data;
  if (!data) {
    return;
  }
  $("pack-name").textContent = data.name;
  $("kind-label").textContent = data.kind;
  $("root-path").textContent = data.root;
  const lock = data.lock;
  $("pin").textContent = lock ? `${lock.source}@${lock.tag}` : data.root;
  document.title = `${data.name} · pack`;
  renderStats(data);
  $("view").innerHTML = views[state.view](data);
}

function openDrawer(kind, id) {
  const data = state.data;
  const item =
    kind === "skill"
      ? data.skills.find((row) => row.id === id)
      : kind === "profile"
        ? data.profiles.find((row) => row.id === id)
        : data.runs.find((row) => row.invocation_id === id);
  if (!item) {
    return;
  }
  $("drawer-kicker").textContent = item.path || item.outcome || kind;
  $("drawer-title").textContent = item.name || item.profile_id || id;
  const body = item.body || `profile: ${item.profile_id}\nrequest: ${item.request_text}\nstarted: ${item.started_at}\ncompleted: ${item.completed_at || "—"}\noutcome: ${item.outcome}`;
  $("drawer-body").innerHTML = renderMarkdown(body);
  $("drawer").hidden = false;
}

async function load() {
  try {
    const resp = await fetch("/api/snapshot");
    if (!resp.ok) {
      throw new Error("snapshot failed");
    }
    state.data = await resp.json();
    $("live").classList.remove("is-stale");
    paint();
  } catch (_err) {
    $("live").classList.add("is-stale");
  }
}

document.querySelector(".nav").addEventListener("click", (event) => {
  const button = event.target.closest("[data-view]");
  if (!button) {
    return;
  }
  state.view = button.dataset.view;
  document.querySelectorAll(".nav button").forEach((node) => node.classList.toggle("is-active", node === button));
  paint();
});

$("view").addEventListener("click", (event) => {
  const button = event.target.closest("[data-kind]");
  if (!button) {
    return;
  }
  openDrawer(button.dataset.kind, button.dataset.id);
});

$("drawer-close").addEventListener("click", () => {
  $("drawer").hidden = true;
});

async function tick() {
  await load();
  setTimeout(tick, 2000);
}

tick();
