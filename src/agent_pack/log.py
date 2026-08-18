from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent_pack.errors import PackError
from agent_pack.lockfile import read_lockfile

LOG_DIR = Path(".agents") / "log"
OUTCOMES = ("done", "failed", "abandoned")

_LOG_README = """# Agent pack run log

JSONL files in this directory are gitignored.

Each `<invocation_id>.jsonl` has a `started` line and optionally a `completed` line.

Write events with `pack record start` and `pack record complete`.
"""

_LOG_SCHEMA = """{
  "started": {
    "event": "started",
    "invocation_id": "string",
    "profile_id": "string",
    "request_text": "string",
    "started_at": "ISO-8601"
  },
  "completed": {
    "event": "completed",
    "invocation_id": "string",
    "outcome": "done | failed | abandoned",
    "completed_at": "ISO-8601"
  }
}
"""


def ensure_log_scaffold(app_root: Path) -> None:
    log_dir = app_root / LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "README.md").write_text(_LOG_README, encoding="utf-8")
    (log_dir / "schema.json").write_text(_LOG_SCHEMA, encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_start(app_root: Path, profile_id: str, request_text: str) -> str:
    read_lockfile(app_root)
    ensure_log_scaffold(app_root)
    invocation_id = uuid.uuid4().hex
    event = {
        "event": "started",
        "invocation_id": invocation_id,
        "profile_id": profile_id,
        "request_text": request_text,
        "started_at": _now(),
    }
    path = app_root / LOG_DIR / f"{invocation_id}.jsonl"
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    return f"{invocation_id}\n"


def record_complete(app_root: Path, invocation_id: str, outcome: str) -> str:
    read_lockfile(app_root)
    if outcome not in OUTCOMES:
        raise PackError(f"outcome must be one of: {', '.join(OUTCOMES)}")
    path = app_root / LOG_DIR / f"{invocation_id}.jsonl"
    if not path.is_file():
        raise PackError(f"no start record: {invocation_id}")
    started, completed = _events(path)
    if started is None:
        raise PackError(f"no started event: {invocation_id}")
    if completed is not None:
        raise PackError(f"already completed: {invocation_id}")
    event = {
        "event": "completed",
        "invocation_id": invocation_id,
        "outcome": outcome,
        "completed_at": _now(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")
    return f"{invocation_id} {outcome}\n"


def _events(path: Path) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    started: dict[str, object] | None = None
    completed: dict[str, object] | None = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None, None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        event = data.get("event")
        if event == "started":
            started = data
            continue
        if event == "completed":
            completed = data
    return started, completed


@dataclass(frozen=True)
class Run:
    invocation_id: str
    profile_id: str
    request_text: str
    started_at: str
    completed_at: str | None
    outcome: str

    def as_dict(self) -> dict[str, str | None]:
        return {
            "invocation_id": self.invocation_id,
            "profile_id": self.profile_id,
            "request_text": self.request_text,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "outcome": self.outcome,
        }


def list_runs(app_root: Path, limit: int | None = None) -> list[Run]:
    if limit is not None and limit < 0:
        raise PackError("limit must be >= 0")
    log_dir = app_root / LOG_DIR
    if not log_dir.is_dir():
        return []
    runs: list[Run] = []
    for path in log_dir.glob("*.jsonl"):
        started, completed = _events(path)
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
            )
        )
    runs.sort(key=lambda run: run.started_at, reverse=True)
    if limit is None:
        return runs
    return runs[:limit]


def format_log(app_root: Path, limit: int) -> str:
    read_lockfile(app_root)
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
