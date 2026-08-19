from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from agent_pack.errors import PackError

PACK_YAML = "pack.yaml"
AGENTS_MD = "AGENTS.md"
CONSTITUTION_MD = "constitution.md"
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PACK_TREES = ("skills", "profiles")
SYNC_SUFFIXES = {".md", ".yaml", ".yml"}

_INIT_PACK_YAML = """name: {name}
description: Team agent skills and profiles. Edit here; consumers bind a tag and sync.
"""

_INIT_AGENTS_MD = """# Agents

Skills and profiles for this team live in the pack repository.

- Skills: `skills/<id>/SKILL.md`
- Profiles: `profiles/<id>.agent.yaml`
- Constitution: `constitution.md` (must / must not)

In an application repo, `pack sync` copies them to `.agents/` and projects skills into `.cursor/skills/` and `.claude/skills/`, profiles into `.claude/agents/`, and a marked block into root `AGENTS.md`. Edit only in this pack; never push consumer edits back upstream.
"""

_INIT_CONSTITUTION = """# Constitution

## Must

Follow pack skills and profiles. Treat pack-managed files in a consumer as read-only.

## Must not

Do not put secrets in source. Do not invent UI components, spacing, or hardcoded colors when the project already has them. Do not edit pack-managed files in a consumer and push those edits upstream.
"""

_INIT_SKILL = """---
name: example
description: Placeholder skill. Replace with a real team skill or delete this folder.
---

# Example

Write the playbook the agent should follow.
"""

_INIT_PROFILE = """profile-id: generic-agent
name: Generic Agent
description: Default profile when no specialist is assigned.
"""

_INIT_VERIFIER = """profile-id: verifier
name: Verifier
description: Refuses merge when work violates the constitution or pack skills.
instructions: |
  Review against constitution.md and pack skills. Say no when code moves
  without an updated contract, secrets appear in source, or UI invents
  components, spacing, or hardcoded colors the project already defines.
  The valuable output is a block, not a rewrite.
"""


def pack_yaml_path(root: Path) -> Path:
    return root / PACK_YAML


def require_pack_root(root: Path) -> Path:
    path = pack_yaml_path(root)
    if not path.is_file():
        raise PackError(f"not a pack repo (missing {PACK_YAML}): {root}")
    return root


def init_pack(root: Path, name: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if pack_yaml_path(root).exists():
        raise PackError(f"{PACK_YAML} already exists in {root}")
    (root / PACK_YAML).write_text(_INIT_PACK_YAML.format(name=name), encoding="utf-8")
    (root / AGENTS_MD).write_text(_INIT_AGENTS_MD, encoding="utf-8")
    (root / CONSTITUTION_MD).write_text(_INIT_CONSTITUTION, encoding="utf-8")
    skill_dir = root / "skills" / "example"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(_INIT_SKILL, encoding="utf-8")
    profiles = root / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    (profiles / "generic-agent.agent.yaml").write_text(_INIT_PROFILE, encoding="utf-8")
    (profiles / "verifier.agent.yaml").write_text(_INIT_VERIFIER, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def posix_rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def safe_dest(app_root: Path, rel: str) -> Path:
    """Pack content decides these paths; never let one escape the consumer root."""
    root = app_root.resolve()
    dest = (root / rel).resolve()
    if dest != root and root not in dest.parents:
        raise PackError(f"refusing to write outside the app root: {rel}")
    return app_root / rel


def _is_sync_file(path: Path) -> bool:
    return path.is_file() and path.suffix in SYNC_SUFFIXES


def iter_pack_files(pack_root: Path) -> list[Path]:
    require_pack_root(pack_root)
    files: list[Path] = [pack_root / PACK_YAML]
    for name in (AGENTS_MD, CONSTITUTION_MD):
        path = pack_root / name
        if path.is_file():
            files.append(path)
    for tree in PACK_TREES:
        base = pack_root / tree
        if not base.exists():
            continue
        files.extend(path for path in sorted(base.rglob("*")) if _is_sync_file(path))
    return files


def consumer_rel(pack_file: Path, pack_root: Path) -> str:
    return f".agents/{posix_rel(pack_root, pack_file)}"


def load_yaml_mapping(path: Path) -> dict[object, object]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise PackError(f"{path.name}: invalid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise PackError(f"{posix_rel(path.parent, path)}: expected a YAML mapping")
    return loaded


def parse_frontmatter(path: Path) -> dict[object, object]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise PackError(f"{path.name}: missing YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise PackError(f"{path.name}: unterminated YAML frontmatter")
    loaded = yaml.safe_load(parts[1]) or {}
    if not isinstance(loaded, dict):
        raise PackError(f"{path.name}: frontmatter must be a mapping")
    return loaded
