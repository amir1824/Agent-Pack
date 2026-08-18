from __future__ import annotations

from pathlib import Path

from agent_pack.adapters import projected_paths
from agent_pack.consumer import Status, status
from agent_pack.errors import PackError
from agent_pack.lockfile import LOCKFILE_NAME, lockfile_path
from agent_pack.log import list_runs
from agent_pack.source import (
    CONSTITUTION_MD,
    PACK_YAML,
    load_yaml_mapping,
    pack_yaml_path,
    parse_frontmatter,
    posix_rel,
)
from agent_pack.validate import validate_pack

COUNT_KEYS = ("open", "done", "failed", "abandoned")


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _kind(root: Path) -> str:
    pack = pack_yaml_path(root).is_file()
    consumer = lockfile_path(root).is_file()
    if pack and consumer:
        return "both"
    if pack:
        return "pack"
    if consumer:
        return "consumer"
    raise PackError(f"not a pack repo and not bound (missing {PACK_YAML} and {LOCKFILE_NAME})")


def _inventory_root(root: Path, kind: str) -> Path:
    if kind == "consumer":
        return root / ".agents"
    return root


def _skills(root: Path, base: Path) -> list[dict[str, str]]:
    skills_dir = base / "skills"
    if not skills_dir.is_dir():
        return []
    items: list[dict[str, str]] = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            meta = parse_frontmatter(skill_md)
        except PackError:
            meta = {}
        items.append(
            {
                "id": skill_md.parent.name,
                "name": str(meta.get("name") or skill_md.parent.name),
                "description": str(meta.get("description") or "").strip(),
                "path": posix_rel(root, skill_md),
                "body": _read(skill_md),
            }
        )
    return items


def _profiles(root: Path, base: Path) -> list[dict[str, str]]:
    profiles_dir = base / "profiles"
    if not profiles_dir.is_dir():
        return []
    items: list[dict[str, str]] = []
    for path in sorted(profiles_dir.glob("*.agent.yaml")):
        try:
            data = load_yaml_mapping(path)
        except PackError:
            data = {}
        profile_id = str(data.get("profile-id") or path.name.removesuffix(".agent.yaml"))
        items.append(
            {
                "id": profile_id,
                "name": str(data.get("name") or profile_id).strip(),
                "description": str(data.get("description") or "").strip(),
                "instructions": str(data.get("instructions") or "").strip(),
                "path": posix_rel(root, path),
                "body": _read(path),
            }
        )
    return items


def _pack_info(root: Path, kind: str) -> dict[str, object] | None:
    if kind == "consumer":
        return None
    try:
        meta = load_yaml_mapping(root / PACK_YAML)
    except PackError:
        meta = {}
    errors = validate_pack(root)
    return {
        "name": str(meta.get("name") or "").strip(),
        "description": str(meta.get("description") or "").strip(),
        "valid": not errors,
        "errors": errors,
    }


def _lock_info(report: Status) -> dict[str, object]:
    lock = report.lock
    state = "clean"
    if not report.synced:
        state = "not synced"
    elif report.dirty:
        state = "dirty"
    return {
        "name": lock.name,
        "source": lock.source,
        "tag": lock.tag,
        "commit": lock.commit,
        "state": state,
        "modified": list(report.modified),
        "missing": list(report.missing),
        "extra": list(report.extra),
    }


def _projections(root: Path, report: Status) -> list[dict[str, object]]:
    return [
        {"path": host_rel, "present": (root / host_rel).is_file(), "source": rel}
        for rel in sorted(report.lock.files)
        for host_rel in projected_paths(rel)
    ]


def _counts(skills: list[dict[str, str]], profiles: list[dict[str, str]], runs: list[dict[str, str | None]]) -> dict[str, int]:
    counts = {"skills": len(skills), "profiles": len(profiles), **{key: 0 for key in COUNT_KEYS}}
    for run in runs:
        outcome = run.get("outcome")
        if outcome in COUNT_KEYS:
            counts[str(outcome)] += 1
    return counts


def build_snapshot(root: Path) -> dict[str, object]:
    root = root.resolve()
    kind = _kind(root)
    base = _inventory_root(root, kind)
    skills = _skills(root, base)
    profiles = _profiles(root, base)
    runs = [run.as_dict() for run in list_runs(root)]
    pack = _pack_info(root, kind)
    report = None if kind == "pack" else status(root)
    lock = _lock_info(report) if report else None
    name = str((pack or {}).get("name") or (lock or {}).get("name") or root.name)
    return {
        "kind": kind,
        "root": str(root),
        "name": name,
        "pack": pack,
        "lock": lock,
        "constitution": _read(base / CONSTITUTION_MD),
        "skills": skills,
        "profiles": profiles,
        "projections": _projections(root, report) if report else [],
        "runs": runs,
        "counts": _counts(skills, profiles, runs),
    }
