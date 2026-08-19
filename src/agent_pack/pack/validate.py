from __future__ import annotations

from pathlib import Path

from agent_pack.errors import PackError
from agent_pack.pack.source import (
    AGENTS_MD,
    CONSTITUTION_MD,
    PACK_YAML,
    SKILL_NAME_RE,
    load_yaml_mapping,
    parse_frontmatter,
    posix_rel,
    require_pack_root,
)


def _reject_symlinks(pack_root: Path) -> list[str]:
    errors: list[str] = []
    roots = [
        pack_root / PACK_YAML,
        pack_root / AGENTS_MD,
        pack_root / CONSTITUTION_MD,
        pack_root / "skills",
        pack_root / "profiles",
    ]
    for root in roots:
        if not root.exists():
            continue
        if root.is_symlink():
            errors.append(f"symlink not allowed: {posix_rel(pack_root, root)}")
            continue
        if root.is_file():
            continue
        errors.extend(
            f"symlink not allowed: {posix_rel(pack_root, path)}"
            for path in root.rglob("*")
            if path.is_symlink()
        )
    return errors


def _validate_skill(pack_root: Path, skill_md: Path) -> tuple[str, list[str]]:
    errors: list[str] = []
    rel = posix_rel(pack_root, skill_md)
    try:
        meta = parse_frontmatter(skill_md)
    except PackError as exc:
        return "", [f"{rel}: {exc}"]
    name = str(meta.get("name") or "")
    description = str(meta.get("description") or "").strip()
    folder = skill_md.parent.name
    if not name:
        errors.append(f"{rel}: frontmatter name is required")
    if name and not SKILL_NAME_RE.fullmatch(name):
        errors.append(f"{rel}: name {name!r} must be lowercase alphanumeric plus hyphens")
    if name and name != folder:
        errors.append(f"{rel}: name {name!r} must match folder {folder!r}")
    if not description:
        errors.append(f"{rel}: frontmatter description is required")
    return name, errors


def _validate_profile(pack_root: Path, path: Path) -> tuple[str, tuple[str, ...], list[str]]:
    errors: list[str] = []
    rel = posix_rel(pack_root, path)
    try:
        data = load_yaml_mapping(path)
    except PackError as exc:
        return "", (), [str(exc)]
    profile_id = str(data.get("profile-id") or "")
    expected = path.name[: -len(".agent.yaml")]
    if not profile_id:
        errors.append(f"{rel}: profile-id is required")
    if profile_id and profile_id != expected:
        errors.append(f"{rel}: profile-id {profile_id!r} must match filename {expected!r}")
    if not str(data.get("name") or "").strip():
        errors.append(f"{rel}: name is required")
    if not str(data.get("description") or "").strip():
        errors.append(f"{rel}: description is required")
    plan_raw = data.get("plan")
    plan: tuple[str, ...] = ()
    if plan_raw is not None:
        if not isinstance(plan_raw, list) or not plan_raw:
            errors.append(f"{rel}: plan must be a non-empty list of step names")
        else:
            items = [str(item).strip() for item in plan_raw]
            if any(not item for item in items):
                errors.append(f"{rel}: plan entries must not be empty")
            elif len(set(items)) != len(items):
                errors.append(f"{rel}: plan entries must be unique")
            else:
                plan = tuple(items)
    return profile_id, plan, errors


def _unique(errors: list[str], seen: dict[str, str], key: str, rel: str, label: str) -> None:
    prior = seen.get(key)
    if prior:
        errors.append(f"duplicate {label} {key!r}: {prior} and {rel}")
        return
    seen[key] = rel


def validate_pack(pack_root: Path) -> list[str]:
    require_pack_root(pack_root)
    errors = _reject_symlinks(pack_root)
    try:
        meta = load_yaml_mapping(pack_root / PACK_YAML)
    except PackError as exc:
        errors.append(str(exc))
        return errors
    if not str(meta.get("name") or "").strip():
        errors.append(f"{PACK_YAML}: name is required")
    if not (pack_root / AGENTS_MD).is_file():
        errors.append(f"missing {AGENTS_MD}")
    constitution = pack_root / CONSTITUTION_MD
    if not constitution.is_file():
        errors.append(f"missing {CONSTITUTION_MD}")
    elif not constitution.read_text(encoding="utf-8").strip():
        errors.append(f"{CONSTITUTION_MD}: must not be empty")
    if not (pack_root / "skills").is_dir():
        errors.append("missing skills/")
    if not (pack_root / "profiles").is_dir():
        errors.append("missing profiles/")

    skill_ids: dict[str, str] = {}
    skill_dir = pack_root / "skills"
    skill_files = sorted(skill_dir.glob("*/SKILL.md")) if skill_dir.is_dir() else []
    for skill_md in skill_files:
        skill_id, skill_errors = _validate_skill(pack_root, skill_md)
        errors.extend(skill_errors)
        if skill_id:
            _unique(errors, skill_ids, skill_id, posix_rel(pack_root, skill_md), "skill id")

    profile_ids: dict[str, str] = {}
    plans: list[tuple[str, tuple[str, ...]]] = []
    profile_dir = pack_root / "profiles"
    yaml_profiles = sorted(profile_dir.glob("*.agent.yaml")) if profile_dir.is_dir() else []
    for path in yaml_profiles:
        profile_id, plan, profile_errors = _validate_profile(pack_root, path)
        errors.extend(profile_errors)
        if profile_id:
            _unique(errors, profile_ids, profile_id, posix_rel(pack_root, path), "profile-id")
            rel = posix_rel(pack_root, path)
            plans.append((rel, plan))

    # A plan names other agents by their profile-id — if the id doesn't exist,
    # "each agent's log" (steps grouped by name) silently loses that agent.
    for rel, plan in plans:
        for step in plan:
            if step not in profile_ids:
                errors.append(f"{rel}: plan step {step!r} does not match any profile-id in profiles/")
    return errors


def require_valid_pack(pack_root: Path) -> Path:
    errors = validate_pack(pack_root)
    if errors:
        raise PackError("pack validate failed:\n" + "\n".join(f"  {item}" for item in errors))
    return pack_root
