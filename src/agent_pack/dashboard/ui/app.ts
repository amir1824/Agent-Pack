import { flowNodes } from "./flow";
import { eventLogEntries, renderLogTimeline, allLogRows, clampLogPage } from "./log_rows";
import { escapeHtml, renderMarkdown } from "./markdown";
import { chip,renderCards, renderOverview, renderRuns, renderStats } from "./views";
import type { Snapshot } from "./types";

type AppState = {
  view: string;
  data: Snapshot | null;
  fingerprint: string;
  selected: { runId: string; index: number } | null;
  logPage: number;
};

const state: AppState = {
  view: "overview",
  data: null,
  fingerprint: "",
  selected: null,
  logPage: 0,
};

const $ = (id: string): HTMLElement => {
  const el = document.getElementById(id);
  if (!el) {
    throw new Error(`missing #${id}`);
  }
  return el;
};

const POLL_ACTIVE_MS = 1000;
const POLL_IDLE_MS = 2000;

function renderConstitution(data: Snapshot): string {
  return `<article class="panel prose">${renderMarkdown(data.constitution)}</article>`;
}

const views: Record<string, (data: Snapshot) => string> = {
  overview: (data) => renderOverview(data),
  runs: (data) => renderRuns(data, state.logPage),
  skills: (data) => renderCards(data.skills, "skill"),
  profiles: (data) => renderCards(data.profiles, "profile"),
  constitution: renderConstitution,
};

function fillDrawer(runId: string, index: number): boolean {
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
  const skillBlock = skill
    ? `<section class="skill-note"><p class="kicker">Skill</p>${renderMarkdown(skill.description)}</section>`
    : "";
  $("drawer-body").innerHTML = `${timeline}${skillBlock}`;
  return true;
}

function snapshotFingerprint(data: Snapshot): string {
  return JSON.stringify({ runs: data.runs, counts: data.counts });
}

function paint(): void {
  const data = state.data;
  if (!data) {
    return;
  }
  const drawer = $("drawer");
  const keepOpen = Boolean(state.selected) && !drawer.hidden;
  const scrollTop = keepOpen ? $("drawer-body").scrollTop : 0;
  $("pack-name").textContent = data.name;
  $("kind-label").textContent = data.kind;
  $("root-path").textContent = data.root;
  const lock = data.lock;
  $("pin").textContent = lock ? `${lock.source}@${lock.tag}` : data.root;
  document.title = `${data.name} · pack`;
  renderStats(data, $("stats"));
  $("view").innerHTML = views[state.view](data);
  if (state.selected && fillDrawer(state.selected.runId, state.selected.index)) {
    drawer.hidden = false;
    if (keepOpen) {
      $("drawer-body").scrollTop = scrollTop;
    }
  }
}

function renderRunBody(id: string): string {
  const run = state.data?.runs.find((row) => row.invocation_id === id);
  if (!run) return "";
  const steps = (run.steps || []).map((step) => `- ${step.name}: ${step.status}`).join("\n");
  const pin = run.pack_tag
    ? `pack: ${run.pack_name ?? "—"}@${run.pack_tag}\ncommit: ${run.pack_commit ?? "—"}\n`
    : "";
  return `${pin}profile: ${run.profile_id}\nrequest: ${run.request_text}\nstarted: ${run.started_at}\ncompleted: ${run.completed_at || "—"}\noutcome: ${run.outcome}\n${steps ? `\nsteps:\n${steps}` : ""}`;
}

function openItemDrawer(kind: string, id: string): void {
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

function openNodeDrawer(runId: string, index: number): void {
  state.selected = { runId, index };
  fillDrawer(runId, index);
  $("drawer").hidden = false;
}

function openDrawerFromElement(button: HTMLElement): void {
  const kind = button.dataset.kind || "";
  if (kind === "start" || kind === "complete" || kind === "step") {
    openNodeDrawer(String(button.dataset.run), Number(button.dataset.index));
    return;
  }
  openItemDrawer(kind, String(button.dataset.id));
}

async function load(): Promise<void> {
  try {
    const resp = await fetch("/api/snapshot");
    if (!resp.ok) {
      throw new Error("snapshot failed");
    }
    const next = (await resp.json()) as Snapshot;
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

async function tick(): Promise<void> {
  await load();
  const open = Boolean(state.data?.runs?.some((run) => run.outcome === "open"));
  setTimeout(tick, open ? POLL_ACTIVE_MS : POLL_IDLE_MS);
}

function boot(): void {
  document.querySelector(".nav")?.addEventListener("click", (event) => {
    const button = (event.target as HTMLElement).closest("[data-view]") as HTMLElement | null;
    if (!button) {
      return;
    }
    state.view = button.dataset.view || "overview";
    document.querySelectorAll(".nav button").forEach((node) => node.classList.toggle("is-active", node === button));
    paint();
  });

  $("view").addEventListener("click", (event) => {
    const target = event.target as HTMLElement;
    const pageBtn = target.closest("[data-log-page]") as HTMLElement | null;
    if (pageBtn && !pageBtn.hasAttribute("disabled")) {
      state.logPage = Number(pageBtn.dataset.logPage);
      paint();
      return;
    }
    const button = target.closest("[data-kind]") as HTMLElement | null;
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
