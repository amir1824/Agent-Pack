from __future__ import annotations

import json
from pathlib import Path

RunEvents = list[dict[str, object]]
StepLogs = dict[str, list[dict[str, str]]]


def parse_plan(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(str(item).strip() for item in raw if str(item).strip())


def step_entry(data: dict[str, object]) -> dict[str, str]:
    return {
        "status": str(data.get("status") or "started"),
        "at": str(data.get("at") or ""),
        "detail": str(data.get("detail") or ""),
    }


def read_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    rows: list[dict[str, object]] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def aggregate_steps(plan: tuple[str, ...], logs: StepLogs, order: list[str]) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    names = list(plan) + [name for name in order if name not in plan]
    for name in names:
        if name not in logs:
            continue
        history = logs[name]
        last = history[-1]
        steps.append(
            {
                "name": name,
                "status": last["status"],
                "at": last["at"],
                "detail": last["detail"],
                "log": [dict(item) for item in history],
            }
        )
    return steps


def collect_step(data: dict[str, object], logs: StepLogs, order: list[str]) -> None:
    label = str(data.get("name") or "").strip()
    if not label:
        return
    if label not in logs:
        logs[label] = []
        order.append(label)
    logs[label].append(step_entry(data))


def parse_run(
    path: Path,
) -> tuple[dict[str, object] | None, dict[str, object] | None, tuple[str, ...], RunEvents, list[dict[str, object]]]:
    started: dict[str, object] | None = None
    completed: dict[str, object] | None = None
    run_events: RunEvents = []
    logs: StepLogs = {}
    order: list[str] = []
    for data in read_jsonl(path):
        event_type = data.get("event")
        if event_type == "started":
            started = data
            run_events.append(dict(data))
            continue
        if event_type == "completed":
            completed = data
            run_events.append(dict(data))
            continue
        if event_type != "step":
            continue
        collect_step(data, logs, order)
    plan = parse_plan(started.get("plan") if started else None)
    steps = aggregate_steps(plan, logs, order)
    return started, completed, plan, run_events, steps
