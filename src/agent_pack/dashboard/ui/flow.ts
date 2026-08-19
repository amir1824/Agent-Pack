import type { ChipFn, EscapeFn, FlowNode, Run, Step } from "./types";

function roleLabel(name: string): string {
  return String(name)
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function stepByName(run: Run): Record<string, Step> {
  return Object.fromEntries((run.steps || []).map((step) => [step.name, step]));
}

export function planPhase(
  name: string,
  index: number,
  activeIndex: number,
  nextIndex: number,
  byName: Record<string, Step>,
): string {
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

function stepNode(step: Step): FlowNode {
  const phase =
    step.status === "started"
      ? "active"
      : step.status === "done"
        ? "done"
        : step.status === "failed"
          ? "failed"
          : "waiting";
  return {
    kind: "step",
    name: step.name,
    label: roleLabel(step.name),
    phase,
    status: step.status,
    at: step.at || "",
    detail: step.detail || "",
    log: step.log || [],
  };
}

function plannedNodes(run: Run, byName: Record<string, Step>): FlowNode[] {
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
      kind: "step" as const,
      name,
      label: roleLabel(name),
      phase,
      status: step?.status || phase,
      at: step?.at || "",
      detail: step?.detail || "",
      log: step?.log || [],
    };
  });
  const extras = (run.steps || []).filter((step) => !plan.includes(step.name)).map(stepNode);
  return [...nodes, ...extras];
}

function completeNode(run: Run): FlowNode {
  const OUTCOME_PHASE: Record<string, string> = { open: "pending", done: "done", failed: "failed", abandoned: "failed" };
  const endPhase = OUTCOME_PHASE[run.outcome] ?? "pending";
  return {
    kind: "complete",
    name: "complete",
    label: "Complete",
    phase: endPhase,
    status: endPhase,
    at: run.completed_at || "",
    detail: run.outcome,
    log: [],
  };
}

export function flowNodes(run: Run): FlowNode[] {
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
      log: [],
    },
    ...plannedNodes(run, byName),
    completeNode(run),
  ];
}

export function flowProgress(run: Run): { done: number; total: number; label: string } {
  const plan = run.plan || [];
  const byName = stepByName(run);
  if (!plan.length) {
    const done = (run.steps || []).filter((step) => step.status === "done").length;
    const total = (run.steps || []).length;
    return { done, total: total || 0, label: total ? `${done}/${total}` : "—" };
  }
  const done = plan.filter((name) => byName[name]?.status === "done").length;
  return { done, total: plan.length, label: `${done}/${plan.length}` };
}

function edgeClass(leftNode: FlowNode): string {
  return leftNode.phase === "done" ? "edge solid" : "edge dashed";
}

function nodeIcon(phase: string): string {
  if (phase === "done") return "✓";
  if (phase === "active") return "●";
  if (phase === "failed") return "✕";
  if (phase === "upcoming") return "○";
  return "·";
}

function renderNode(run: Run, node: FlowNode, index: number, escapeHtml: EscapeFn): string {
  return `
    <button type="button" class="node ${escapeHtml(node.phase)}" data-kind="${escapeHtml(node.kind)}" data-run="${escapeHtml(run.invocation_id)}" data-index="${index}">
      <span class="node-icon" aria-hidden="true">${nodeIcon(node.phase)}</span>
      <strong>${escapeHtml(node.label || node.name)}</strong>
      <span>${escapeHtml(node.phase)}</span>
    </button>`;
}

export function renderFlow(run: Run, escapeHtml: EscapeFn, chip: ChipFn): string {
  const nodes = flowNodes(run);
  const progress = flowProgress(run);
  const strip = nodes
    .map(
      (node, index) =>
        `${index ? `<i class="${edgeClass(nodes[index - 1])}"></i>` : ""}${renderNode(run, node, index, escapeHtml)}`,
    )
    .join("");
  return `
    <article class="panel flow hero">
      <div class="flow-head">
        <div>
          <p class="kicker">Live flow</p>
          <h3>${escapeHtml(run.profile_id)} · ${escapeHtml(run.request_text || "open run")}</h3>
        </div>
        <div class="flow-meta">
          <span class="progress">${escapeHtml(progress.label)}</span>
          ${chip("open", "warn")}
        </div>
      </div>
      <div class="strip">${strip}</div>
    </article>`;
}

