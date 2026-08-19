import { eventLogEntries, renderLogTimeline, allLogRows, clampLogPage } from "./log_rows";
import { renderMarkdown } from "./markdown";
import { renderCards, renderOverview, renderRuns, renderStats } from "./views";
import {
  bootUpgrade,
  handleUpgradeClick,
  upgradeBanner,
  type UpgradeContext,
} from "./upgrade";
import { fillDrawer, openDrawerFromElement, restoreDrawer, type DrawerHost } from "./drawer";
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

const drawerHost: DrawerHost = {
  getData: () => state.data,
  getSelected: () => state.selected,
  setSelected: (value) => {
    state.selected = value;
  },
  $,
};

const upgradeCtx: UpgradeContext = {
  view: state.view,
  getData: () => state.data,
  paint,
  reloadSnapshot: load,
  resetFingerprint: () => {
    state.fingerprint = "";
  },
};

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

function viewLabel(): string {
  return (
    document.querySelector(`.nav [data-view="${state.view}"]`)?.textContent?.trim() ||
    state.view
  );
}

function snapshotFingerprint(data: Snapshot): string {
  return JSON.stringify({ runs: data.runs, counts: data.counts });
}

function paint(): void {
  const data = state.data;
  if (!data) {
    return;
  }
  upgradeCtx.view = state.view;
  const drawer = $("drawer");
  const keepOpen = Boolean(state.selected) && !drawer.hidden;
  const scrollTop = keepOpen ? $("drawer-body").scrollTop : 0;
  const label = viewLabel();
  $("view-title").textContent = label;
  $("kind-label").textContent = data.kind;
  $("root-path").textContent = data.root;
  const lock = data.lock;
  $("pin").textContent = lock ? `${lock.source}@${lock.tag}` : data.root;
  document.title = `${label} · agent-pack`;
  renderStats(data, $("stats"));
  $("view").innerHTML = upgradeBanner(upgradeCtx) + views[state.view](data);
  if (restoreDrawer(drawerHost)) {
    drawer.hidden = false;
    if (keepOpen) {
      $("drawer-body").scrollTop = scrollTop;
    }
  }
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
    if (handleUpgradeClick(target, upgradeCtx)) {
      return;
    }
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
    openDrawerFromElement(drawerHost, button);
  });

  $("drawer-close").addEventListener("click", () => {
    state.selected = null;
    $("drawer").hidden = true;
  });

  void tick();
  bootUpgrade(upgradeCtx);
}

if (typeof document !== "undefined" && document.getElementById("view")) {
  boot();
}
