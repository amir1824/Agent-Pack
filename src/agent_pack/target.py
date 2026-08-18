from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_pack.errors import PackError
from agent_pack.gitutil import clone, repo_basename


@dataclass(frozen=True)
class Target:
    root: Path


def resolve_target(directory: str | None, repo: str | None, *, create: bool = False) -> Target:
    if directory and repo:
        raise PackError("use either -C or --repo, not both")
    if directory:
        root = Path(directory).expanduser().resolve()
        if create:
            root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir():
            raise PackError(f"directory not found: {root}")
        return Target(root)
    if repo:
        dest = Path.cwd() / repo_basename(repo)
        if not dest.exists():
            clone(repo, dest)
        if not dest.is_dir():
            raise PackError(f"clone destination is not a directory: {dest}")
        return Target(dest.resolve())
    return Target(Path.cwd())
