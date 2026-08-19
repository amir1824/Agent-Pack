import type { ChipFn, EscapeFn, FlowNode, Run, StepLogEntry, TimelineRow } from "./types";

export const LOG_PAGE_SIZE = 25;

export function renderLogTimeline(entries: StepLogEntry[], escapeHtml: EscapeFn, chip: ChipFn): string {
  if (!entries.length) return '<p class="muted">No log entries yet.</p>';
  return `<ol class="log-timeline">${entries
    .map(
      (entry) => `
        <li class="log-entry ${escapeHtml(entry.status || "pending")}">
          <time>${escapeHtml(entry.at || "—")}</time>
          ${chip(entry.status || "pending", entry.status === "done" ? "ok" : entry.status === "failed" ? "bad" : "warn")}
          <p>${escapeHtml(entry.detail || "—")}</p>
        </li>`,
    )
    .join("")}</ol>`;
}

export function eventLogEntries(run: Run, node: FlowNode): StepLogEntry[] {
  if (node.kind === "start") {
    return (run.events || [])
      .filter((event) => event.event === "started")
      .map((event) => ({ status: "started", at: event.started_at ?? "", detail: event.request_text ?? "" }));
  }
  if (node.kind === "complete") {
    const completed = (run.events || []).find((event) => event.event === "completed");
    if (completed) return [{ status: completed.outcome ?? "completed", at: completed.completed_at ?? "", detail: `Run ${completed.outcome ?? "closed"}` }];
    return [{ status: "pending", at: "—", detail: "Still running" }];
  }
  return node.log || [];
}

function runTimeline(run: Run): { at: string; kind: string; label: string }[] {
  const eventRows = (run.events || []).map((event) => ({
    at: event.started_at ?? event.completed_at ?? "",
    kind: event.event ?? "",
    label: event.request_text ?? event.outcome ?? "",
  }));
  const stepRows = (run.steps || []).flatMap((step) =>
    (step.log || []).map((entry) => ({
      at: entry.at ?? "",
      kind: "step",
      label: `${step.name}: ${entry.status}${entry.detail ? ` — ${entry.detail}` : ""}`,
    })),
  );
  return [...eventRows, ...stepRows].sort((left, right) => left.at.localeCompare(right.at));
}

export function allLogRows(runs: Run[]): TimelineRow[] {
  return runs
    .flatMap((run) =>
      runTimeline(run).map((row) => ({
        at: row.at,
        kind: row.kind,
        runId: run.invocation_id,
        profile: run.profile_id,
        detail: row.label,
      })),
    )
    .sort((left, right) => right.at.localeCompare(left.at));
}

export function clampLogPage(page: number, totalRows: number): number {
  const maxPage = Math.max(0, Math.ceil(totalRows / LOG_PAGE_SIZE) - 1);
  return Math.min(Math.max(page, 0), maxPage);
}
