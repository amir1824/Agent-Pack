from __future__ import annotations

from pathlib import Path

LOG_DIR = Path(".agents") / "log"

_LOG_README = """# Agent pack run log

JSONL files in this directory are gitignored — this is local observability,
not durable evidence. It does not survive a fresh checkout or a rebuilt CI
runner, so it does not outlive the machine on its own.

To keep a run as evidence, archive it: `pack log --export <path>` writes every
run as a single JSON document, suitable for uploading as a CI artifact or
committing wherever your team keeps audit records — outside this directory.

Each `<invocation_id>.jsonl` has a `started` line (optional `plan`, and
`pack_name`/`pack_tag`/`pack_commit` when the run happened in a bound
consumer — that is the pin that was in force, i.e. which version of the
constitution and skills governed the run), `step` lines, and optionally a
`completed` line.

Write events with `pack record start`, `pack record step`, and `pack record
complete`. A run's `plan` defaults to the `plan:` declared on its profile
(`profiles/<profile-id>.agent.yaml`) unless `--plan` overrides it. When a plan
is set, `record step` rejects a step name outside it and `record complete
--outcome done` refuses to close the run until every planned step reached
`done` — both accept `--force` to override.
"""

_LOG_SCHEMA = """{
  "started": {
    "event": "started",
    "invocation_id": "string",
    "profile_id": "string",
    "request_text": "string",
    "started_at": "ISO-8601",
    "plan": ["step-a", "step-b"],
    "pack_name": "string, optional — from agent-pack.lock.json",
    "pack_tag": "string, optional — the pinned tag in force for this run",
    "pack_commit": "string, optional — the pinned commit in force for this run"
  },
  "step": {
    "event": "step",
    "invocation_id": "string",
    "name": "string",
    "status": "started | done | failed",
    "detail": "string",
    "at": "ISO-8601"
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
    from agent_pack.sync.gitignore import ensure_gitignore

    log_dir = app_root / LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    readme = log_dir / "README.md"
    if not readme.is_file():
        readme.write_text(_LOG_README, encoding="utf-8")
    schema = log_dir / "schema.json"
    if not schema.is_file():
        schema.write_text(_LOG_SCHEMA, encoding="utf-8")
    ensure_gitignore(app_root)
