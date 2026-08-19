from __future__ import annotations

import os
import shutil
from pathlib import Path

import yaml

from agent_pack.pack import AGENTS_MD, CONSTITUTION_MD, load_yaml_mapping, safe_dest, sha256_file
from agent_pack.sync.lockfile import Lockfile

SKILL_PREFIX = ".agents/skills/"
PROFILE_PREFIX = ".agents/profiles/"
PROFILE_SUFFIX = ".agent.yaml"
HOST_SKILL_ROOTS = (".cursor/skills", ".claude/skills")
BLOCK_START = "<!-- agent-pack:start -->"
BLOCK_END = "<!-- agent-pack:end -->"


def projected_paths(rel: str) -> list[str]:
    if rel.startswith(SKILL_PREFIX):
        rest = rel[len(SKILL_PREFIX) :]
        return [f"{root}/{rest}" for root in HOST_SKILL_ROOTS]
    if rel.startswith(PROFILE_PREFIX) and rel.endswith(PROFILE_SUFFIX):
        profile_id = Path(rel).name[: -len(PROFILE_SUFFIX)]
        return [f".claude/agents/{profile_id}.md"]
    return []


def render_claude_agent(yaml_path: Path) -> str:
    data = load_yaml_mapping(yaml_path)
    profile_id = str(data.get("profile-id") or "")
    description = str(data.get("description") or "").strip()
    instructions = str(data.get("instructions") or "").strip() or description
    frontmatter = yaml.safe_dump(
        {"name": profile_id, "description": description},
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    return f"---\n{frontmatter}\n---\n\n{instructions}\n"


def _replace_dest(dest: Path, payload: Path | str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.packtmp")
    try:
        if isinstance(payload, str):
            tmp.write_text(payload, encoding="utf-8")
        else:
            shutil.copyfile(payload, tmp)
        os.replace(tmp, dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def install_projections(app_root: Path, rel: str, src: Path) -> dict[str, str]:
    written: dict[str, str] = {}
    for host_rel in projected_paths(rel):
        dest = safe_dest(app_root, host_rel)
        payload: Path | str = render_claude_agent(src) if rel.startswith(PROFILE_PREFIX) else src
        _replace_dest(dest, payload)
        written[host_rel] = sha256_file(dest)
    return written


def upsert_root_agents_md(app_root: Path, lock: Lockfile) -> None:
    pack_agents = (app_root / ".agents" / AGENTS_MD).read_text(encoding="utf-8")
    constitution_path = app_root / ".agents" / CONSTITUTION_MD
    constitution = constitution_path.read_text(encoding="utf-8").rstrip("\n") if constitution_path.is_file() else ""
    body = pack_agents.rstrip("\n")
    if constitution:
        body = f"{constitution}\n\n{body}"
    block = f"{BLOCK_START}\npin: {lock.name} {lock.source}@{lock.tag}\n\n{body}\n{BLOCK_END}\n"
    path = app_root / AGENTS_MD
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    _replace_dest(path, _replace_block(existing, block))


def _replace_block(text: str, block: str) -> str:
    start = text.find(BLOCK_START)
    if start == -1:
        prefix = text if not text or text.endswith("\n") else f"{text}\n"
        glue = "\n" if prefix else ""
        return f"{prefix}{glue}{block}"
    end = text.find(BLOCK_END, start + len(BLOCK_START))
    if end == -1:
        return f"{text[:start]}{block}"
    suffix = text[end + len(BLOCK_END) :]
    if suffix.startswith("\n"):
        suffix = suffix[1:]
    return f"{text[:start]}{block}{suffix}"
