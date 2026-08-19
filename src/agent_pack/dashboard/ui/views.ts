import { renderFlow } from "./flow";
import { LOG_PAGE_SIZE, allLogRows } from "./log_rows";
import { escapeHtml } from "./markdown";
import type { Profile, Skill, Snapshot, TimelineRow, UpgradeStatus } from "./types";

const LANES = ["done", "failed", "abandoned"] as const;

export function renderStats(data: Snapshot, statsEl: HTMLElement): void {
  const counts = data.counts;
  statsEl.innerHTML = ["skills", "profiles", "open", "done"]
    .map((key) => `<div><dt>${key}</dt><dd>${counts[key] ?? 0}</dd></div>`)
    .join("");
}

export function chip(label: string, tone: string): string {
  return `<span class="chip ${tone}">${escapeHtml(label)}</span>`;
}

function toneFor(stateLabel: string): string {
  if (stateLabel === "clean" || stateLabel === "valid") return "ok";
  if (stateLabel === "dirty" || stateLabel === "not synced") return "warn";
  return "bad";
}

export function renderUpgradeBanner(status: UpgradeStatus | null, busy = false): string {
  if (!status) {
    return "";
  }
  const checkBtn = `<button type="button" class="ghost" data-upgrade-check${busy ? " disabled" : ""}>Check again</button>`;
  const upgradeBtn = `<button type="button" class="ghost upgrade-run" data-upgrade-run${busy ? " disabled" : ""}>Upgrade</button>`;
  if (status.error) {
    return `<article class="panel upgrade-banner upgrade-banner-error stack">
      <p class="kicker">Update check</p>
      <p class="muted">${escapeHtml(status.error)}</p>
      <div class="upgrade-actions">
        ${checkBtn}
        ${status.available ? upgradeBtn : ""}
      </div>
    </article>`;
  }
  if (!status.available) {
    return "";
  }
  const message = status.tag_moved
    ? `Pinned tag ${status.current_tag} moved on the remote.`
    : `${status.latest_tag} is available (pinned: ${status.current_tag}).`;
  const busyNote = busy ? `<p class="muted">Upgrading…</p>` : "";
  return `<article class="panel upgrade-banner stack">
    <p class="kicker">Update available</p>
    <p>${escapeHtml(message)}</p>
    ${busyNote}
    <div class="upgrade-actions">
      ${checkBtn}
      ${upgradeBtn}
    </div>
  </article>`;
}

export function renderOverview(data: Snapshot): string {
  const pack = data.pack;
  const lock = data.lock;
  const errors =
    pack && pack.errors.length
      ? `<ul class="errors">${pack.errors.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
      : "";
  const projections = data.projections.length
    ? `<table class="table"><thead><tr><th>Host path</th><th>Source</th><th></th></tr></thead><tbody>${data.projections
        .map(
          (row) =>
            `<tr><td>${escapeHtml(row.path)}</td><td>${escapeHtml(row.source)}</td><td>${row.present ? chip("present", "ok") : chip("missing", "bad")}</td></tr>`,
        )
        .join("")}</tbody></table>`
    : '<p class="muted">No host projections in this checkout.</p>';
  const lockState = lock ? chip(lock.state, toneFor(lock.state)) : "";
  const valid = pack ? chip(pack.valid ? "valid" : "invalid", pack.valid ? "ok" : "bad") : "";
  return `
    <div class="grid">
      <article class="panel">
        <p class="kicker">Checkout</p>
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

function eventTone(kind: string): string {
  if (kind === "completed" || kind === "done") return "ok";
  if (kind === "failed" || kind === "abandoned") return "bad";
  return "warn";
}

function renderLogTable(rows: TimelineRow[], page: number): string {
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
  const body = slice
    .map(
      (row) => `
      <tr>
        <td class="mono num">${escapeHtml(row.at || "—")}</td>
        <td>${chip(row.kind, eventTone(row.kind))}</td>
        <td class="mono"><span class="run-id">${escapeHtml(row.runId.slice(0, 12))}</span> <span class="muted">${escapeHtml(row.profile)}</span></td>
        <td>${escapeHtml(row.detail)}</td>
      </tr>`,
    )
    .join("");
  return `<section class="log-panel panel">
    <div class="log-head">
      <p class="kicker">Log</p>
      <div class="pager">
        <span class="pager-meta">Showing ${from}–${to} of ${total}</span>
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

export function renderRuns(data: Snapshot, logPage: number): string {
  const live = (data.runs || [])
    .filter((run) => run.outcome === "open")
    .map((run) => renderFlow(run, escapeHtml, chip))
    .join("");
  const lanes = LANES.map((lane) => {
    const cards =
      data.runs
        .filter((run) => run.outcome === lane)
        .map(
          (run) => `
          <button type="button" class="run" data-kind="run" data-id="${escapeHtml(run.invocation_id)}">
            <strong>${escapeHtml(run.profile_id)}</strong>
            ${escapeHtml(run.request_text || "—")}
            <span class="mono num">${escapeHtml(run.started_at)}</span>
            ${run.pack_tag ? chip(run.pack_tag, "ok") : ""}
          </button>`,
        )
        .join("") || '<p class="muted">None</p>';
    return `<section class="lane ${lane}"><h3>${lane}<span class="num">${data.counts[lane]}</span></h3>${cards}</section>`;
  }).join("");
  const rows = allLogRows(data.runs || []);
  return `${live}<div class="board">${lanes}</div>${renderLogTable(rows, logPage)}`;
}

export function renderCards(items: Skill[] | Profile[], kind: string): string {
  if (!items.length) {
    return `<p class="empty">No ${kind} in this checkout.</p>`;
  }
  return `<div class="grid">${items
    .map(
      (item) => `
        <button type="button" class="card" data-kind="${kind}" data-id="${escapeHtml(item.id)}">
          <p class="kicker">${escapeHtml(kind)}</p>
          <h3>${escapeHtml(item.name || item.id)}</h3>
          ${item.description ? `<p class="muted">${escapeHtml(item.description)}</p>` : ""}
        </button>`,
    )
    .join("")}</div>`;
}
