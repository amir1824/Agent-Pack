from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent_pack.errors import PackError
from agent_pack.log.parse import parse_plan, parse_run
from agent_pack.log.scaffold import LOG_DIR, ensure_log_scaffold
from agent_pack.pack import PACK_YAML, load_yaml_mapping, pack_yaml_path
from agent_pack.sync.lockfile import LOCKFILE_NAME, lockfile_path, read_lockfile

OUTCOMES = ("done", "failed", "abandoned")
STEP_STATUSES = ("started", "done", "failed")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_record_root(app_root: Path) -> None:
    if pack_yaml_path(app_root).is_file() or lockfile_path(app_root).is_file():
        return
    raise PackError(f"not a pack repo and not bound (missing {PACK_YAML} and {LOCKFILE_NAME})")


def _profile_plan(app_root: Path, profile_id: str) -> tuple[str, ...]:
    """The plan declared on the synced profile, so a run's workflow comes from
    the pack (pinned, distributed) rather than being retyped at the CLI."""
    for rel in (
        Path(".agents") / "profiles" / f"{profile_id}.agent.yaml",
        Path("profiles") / f"{profile_id}.agent.yaml",
    ):
        path = app_root / rel
        if not path.is_file():
            continue
        try:
            data = load_yaml_mapping(path)
        except PackError as exc:
            raise PackError(f"cannot read profile plan from {rel}: {exc}") from exc
        return parse_plan(data.get("plan"))
    return ()


def _run_participants(app_root: Path, invocation_id: str) -> tuple[str, ...]:
    """The step names that actually ran in a prior invocation, in the order
    they first appeared — the real roster, as opposed to a static plan that
    may have been partially skipped."""
    path = _log_path(app_root, invocation_id)
    if not path.is_file():
        raise PackError(f"no start record: {invocation_id}")
    started, _completed, _plan, _events, steps = parse_run(path)
    if started is None:
        raise PackError(f"no started event: {invocation_id}")
    return tuple(str(step["name"]) for step in steps)


def _pin_fields(app_root: Path) -> dict[str, str]:
    """Which pack tag/commit was in force for this run, so the log can answer
    'under which constitution did this happen?' — absent for a pack-repo-only
    run (no lockfile) rather than failing the run."""
    if not lockfile_path(app_root).is_file():
        return {}
    try:
        lock = read_lockfile(app_root)
    except PackError:
        return {}
    return {"pack_name": lock.name, "pack_tag": lock.tag, "pack_commit": lock.commit}


def record_start(
    app_root: Path,
    profile_id: str,
    request_text: str,
    plan: tuple[str, ...] = (),
    *,
    from_run: str | None = None,
) -> str:
    _require_record_root(app_root)
    ensure_log_scaffold(app_root)
    invocation_id = uuid.uuid4().hex
    # Precedence: an explicit --plan always wins; --from-run derives the roster
    # from what actually ran in a prior invocation (e.g. a retrospective on
    # whichever agents really participated); otherwise fall back to the
    # profile's own declared plan.
    derived_from_run = False
    if plan:
        resolved_plan = plan
    elif from_run:
        resolved_plan = _run_participants(app_root, from_run)
        derived_from_run = True
    else:
        resolved_plan = _profile_plan(app_root, profile_id)
    if profile_id == "retrospective" and not from_run:
        raise PackError("retrospective runs require --from-run <invocation-id>")
    if derived_from_run and not resolved_plan:
        raise PackError(f"--from-run {from_run}: no recorded steps to derive a plan from")
    event: dict[str, object] = {
        "event": "started",
        "invocation_id": invocation_id,
        "profile_id": profile_id,
        "request_text": request_text,
        "started_at": _now(),
    }
    if resolved_plan:
        event["plan"] = list(resolved_plan)
    if derived_from_run and from_run:
        event["from_run"] = from_run
    event.update(_pin_fields(app_root))
    path = app_root / LOG_DIR / f"{invocation_id}.jsonl"
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    return invocation_id


def _log_path(app_root: Path, invocation_id: str) -> Path:
    if Path(invocation_id).name != invocation_id:
        raise PackError("invalid invocation id")
    return app_root / LOG_DIR / f"{invocation_id}.jsonl"


def _step_properly_done(step: dict[str, object]) -> bool:
    if step.get("status") != "done":
        return False
    log = step.get("log")
    if not isinstance(log, list):
        return False
    saw_started = False
    for entry in log:
        if not isinstance(entry, dict):
            continue
        status = entry.get("status")
        if status == "started":
            saw_started = True
        if status == "done" and not saw_started:
            return False
    return saw_started


def _require_open_run(
    path: Path, invocation_id: str
) -> tuple[dict[str, object] | None, dict[str, object] | None, tuple[str, ...], list[dict[str, object]], list[dict[str, object]]]:
    # ponytail: full JSONL parse on every append; upgrade path = tail-read for completed line only
    if not path.is_file():
        raise PackError(f"no start record: {invocation_id}")
    parsed = parse_run(path)
    started, completed, _plan, _events, _steps = parsed
    if started is None:
        raise PackError(f"no started event: {invocation_id}")
    if completed is not None:
        raise PackError(f"already completed: {invocation_id}")
    return parsed


def record_step(
    app_root: Path, invocation_id: str, name: str, status: str, detail: str = "", *, force: bool = False
) -> str:
    _require_record_root(app_root)
    label = name.strip()
    if not label:
        raise PackError("step name is required")
    if status not in STEP_STATUSES:
        raise PackError(f"status must be one of: {', '.join(STEP_STATUSES)}")
    path = _log_path(app_root, invocation_id)
    _started, _completed, plan, _events, _steps = _require_open_run(path, invocation_id)
    if plan and label not in plan and not force:
        raise PackError(
            f"step {label!r} is not in the plan: {', '.join(plan)}\n"
            "  Use a planned step name, or override with --force."
        )
    event: dict[str, str] = {
        "event": "step",
        "invocation_id": invocation_id,
        "name": label,
        "status": status,
        "at": _now(),
    }
    if detail:
        event["detail"] = detail
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")
    return f"{invocation_id} {label} {status}"


def record_complete(app_root: Path, invocation_id: str, outcome: str, *, force: bool = False) -> str:
    _require_record_root(app_root)
    if outcome not in OUTCOMES:
        raise PackError(f"outcome must be one of: {', '.join(OUTCOMES)}")
    path = _log_path(app_root, invocation_id)
    _started, _completed, plan, _events, steps = _require_open_run(path, invocation_id)
    if outcome == "done" and plan and not force:
        done = {step["name"] for step in steps if _step_properly_done(step)}
        missing = [name for name in plan if name not in done]
        if missing:
            raise PackError(
                f"cannot complete as done: steps not finished: {', '.join(missing)}\n"
                "  Finish them with pack record step --status done, or override with --force."
            )
    event = {
        "event": "completed",
        "invocation_id": invocation_id,
        "outcome": outcome,
        "completed_at": _now(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")
    return f"{invocation_id} {outcome}"


@dataclass(frozen=True)
class Run:
    invocation_id: str
    profile_id: str
    request_text: str
    started_at: str
    completed_at: str | None
    outcome: str
    plan: tuple[str, ...]
    steps: tuple[dict[str, object], ...]
    events: tuple[dict[str, object], ...]
    pack_name: str | None = None
    pack_tag: str | None = None
    pack_commit: str | None = None
    from_run: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "invocation_id": self.invocation_id,
            "profile_id": self.profile_id,
            "request_text": self.request_text,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "outcome": self.outcome,
            "plan": list(self.plan),
            "steps": [dict(step) for step in self.steps],
            "events": [dict(event) for event in self.events],
            "pack_name": self.pack_name,
            "pack_tag": self.pack_tag,
            "pack_commit": self.pack_commit,
            "from_run": self.from_run,
        }


def list_runs(app_root: Path, limit: int | None = None) -> list[Run]:
    if limit is not None and limit < 0:
        raise PackError("limit must be >= 0")
    log_dir = app_root / LOG_DIR
    if not log_dir.is_dir():
        return []
    runs: list[Run] = []
    for path in log_dir.glob("*.jsonl"):
        started, completed, plan, events, steps = parse_run(path)
        if started is None:
            continue
        completed_at = None
        if completed and completed.get("completed_at"):
            completed_at = str(completed.get("completed_at"))
        outcome = str(completed.get("outcome") or "open") if completed else "open"
        runs.append(
            Run(
                invocation_id=str(started.get("invocation_id") or path.stem),
                profile_id=str(started.get("profile_id") or "-"),
                request_text=str(started.get("request_text") or ""),
                started_at=str(started.get("started_at") or "-"),
                completed_at=completed_at,
                outcome=outcome,
                plan=plan,
                steps=tuple(steps),
                events=tuple(events),
                pack_name=str(started["pack_name"]) if started.get("pack_name") else None,
                pack_tag=str(started["pack_tag"]) if started.get("pack_tag") else None,
                pack_commit=str(started["pack_commit"]) if started.get("pack_commit") else None,
                from_run=str(started["from_run"]) if started.get("from_run") else None,
            )
        )
    runs.sort(key=lambda run: run.started_at, reverse=True)
    if limit is None:
        return runs
    return runs[:limit]


def agent_steps(app_root: Path, agent: str) -> list[dict[str, object]]:
    """Every step named `agent` across every run — what one agent has actually
    done, independent of which delivery run it happened in. This is the data
    a retrospective needs and has no other way to get: pack is the only thing
    that has seen every run."""
    entries: list[dict[str, object]] = []
    for run in list_runs(app_root):
        for step in run.steps:
            if step.get("name") != agent:
                continue
            entries.append(
                {
                    "invocation_id": run.invocation_id,
                    "request_text": run.request_text,
                    "run_started_at": run.started_at,
                    "pack_tag": run.pack_tag,
                    "status": step.get("status"),
                    "at": step.get("at"),
                    "detail": step.get("detail", ""),
                }
            )
    entries.sort(key=lambda entry: str(entry["at"] or entry["run_started_at"]), reverse=True)
    return entries


def format_agent_log(app_root: Path, agent: str, limit: int) -> str:
    _require_record_root(app_root)
    entries = agent_steps(app_root, agent)[:limit]
    if not entries:
        return f"no steps recorded for {agent!r}\n"
    headers = ("RUN", "AT", "STATUS", "TAG", "DETAIL")
    display = [
        (
            str(entry["invocation_id"])[:12],
            str(entry["at"] or "-"),
            str(entry["status"] or "-"),
            str(entry["pack_tag"] or "-"),
            str(entry["detail"]).replace("\n", " ")[:40],
        )
        for entry in entries
    ]
    widths = [max(len(headers[i]), max((len(row[i]) for row in display), default=0)) for i in range(5)]
    header = "  ".join(headers[i].ljust(widths[i]) for i in range(5))
    body = "\n".join("  ".join(row[i].ljust(widths[i]) for i in range(5)) for row in display)
    return f"{header}\n{body}\n"


def export_agent_log(app_root: Path, agent: str) -> tuple[str, int]:
    _require_record_root(app_root)
    entries = agent_steps(app_root, agent)
    return json.dumps(entries, indent=2) + "\n", len(entries)


def export_log(app_root: Path) -> tuple[str, int]:
    """Every run as a JSON array — for archiving as a CI artifact, since
    .agents/log/ itself is gitignored and does not outlive the checkout."""
    _require_record_root(app_root)
    runs = list_runs(app_root)
    content = json.dumps([run.as_dict() for run in runs], indent=2) + "\n"
    return content, len(runs)


def format_log(app_root: Path, limit: int) -> str:
    _require_record_root(app_root)
    runs = list_runs(app_root, limit)
    if not runs:
        return "no run records\n"
    headers = ("ID", "PROFILE", "STARTED", "OUTCOME", "REQUEST")
    display = [
        (
            run.invocation_id[:12],
            run.profile_id,
            run.started_at,
            run.outcome,
            run.request_text.replace("\n", " ")[:40],
        )
        for run in runs
    ]
    widths = [max(len(headers[i]), max((len(row[i]) for row in display), default=0)) for i in range(5)]
    header = "  ".join(headers[i].ljust(widths[i]) for i in range(5))
    body = "\n".join("  ".join(row[i].ljust(widths[i]) for i in range(5)) for row in display)
    return f"{header}\n{body}\n"
