import { flowNodes } from "./flow";
import { eventLogEntries, renderLogTimeline } from "./log_rows";
import { escapeHtml, renderMarkdown } from "./markdown";
import { chip } from "./views";
import type { Snapshot } from "./types";

type DrawerHost = {
  getData: () => Snapshot | null;
  getSelected: () => { runId: string; index: number } | null;
  setSelected: (value: { runId: string; index: number } | null) => void;
  $(id: string): HTMLElement;
};

function renderRunBody(data: Snapshot, id: string): string {
  const run = data.runs.find((row) => row.invocation_id === id);
  if (!run) return "";
  const steps = (run.steps || []).map((step) => `- ${step.name}: ${step.status}`).join("\n");
  const pin = run.pack_tag
    ? `pack: ${run.pack_name ?? "—"}@${run.pack_tag}\ncommit: ${run.pack_commit ?? "—"}\n`
    : "";
  return `${pin}profile: ${run.profile_id}\nrequest: ${run.request_text}\nstarted: ${run.started_at}\ncompleted: ${run.completed_at || "—"}\noutcome: ${run.outcome}\n${steps ? `\nsteps:\n${steps}` : ""}`;
}

export function fillDrawer(host: DrawerHost, runId: string, index: number): boolean {
  const data = host.getData();
  if (!data) {
    return false;
  }
  const run = data.runs.find((row) => row.invocation_id === runId);
  const node = run && flowNodes(run)[index];
  if (!node) {
    return false;
  }
  host.$("drawer-kicker").textContent = node.phase || node.kind;
  host.$("drawer-title").textContent = node.label || node.name;
  const skill = node.kind === "step" ? data.skills.find((row) => row.id === node.name) : null;
  const timeline = renderLogTimeline(eventLogEntries(run, node), escapeHtml, chip);
  const skillBlock = skill
    ? `<section class="skill-note"><p class="kicker">Skill</p>${renderMarkdown(skill.description)}</section>`
    : "";
  host.$("drawer-body").innerHTML = `${timeline}${skillBlock}`;
  return true;
}

function openItemDrawer(host: DrawerHost, kind: string, id: string): void {
  const data = host.getData();
  if (!data) return;
  host.setSelected(null);
  const skill = kind === "skill" ? data.skills.find((row) => row.id === id) : null;
  const profile = kind === "profile" ? data.profiles.find((row) => row.id === id) : null;
  const run = kind === "run" ? data.runs.find((row) => row.invocation_id === id) : null;
  host.$("drawer-kicker").textContent = skill?.path || run?.outcome || kind;
  host.$("drawer-title").textContent = skill?.name || profile?.name || run?.profile_id || id;
  const body = skill?.body || profile?.body || (run ? renderRunBody(data, id) : "");
  host.$("drawer-body").innerHTML = renderMarkdown(body);
  host.$("drawer").hidden = false;
}

function openNodeDrawer(host: DrawerHost, runId: string, index: number): void {
  host.setSelected({ runId, index });
  fillDrawer(host, runId, index);
  host.$("drawer").hidden = false;
}

export function openDrawerFromElement(host: DrawerHost, button: HTMLElement): void {
  const kind = button.dataset.kind || "";
  if (kind === "start" || kind === "complete" || kind === "step") {
    openNodeDrawer(host, String(button.dataset.run), Number(button.dataset.index));
    return;
  }
  openItemDrawer(host, kind, String(button.dataset.id));
}

export function restoreDrawer(host: DrawerHost): boolean {
  const selected = host.getSelected();
  if (!selected) {
    return false;
  }
  return fillDrawer(host, selected.runId, selected.index);
}

export type { DrawerHost };
