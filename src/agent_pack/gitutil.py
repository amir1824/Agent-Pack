from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from agent_pack.errors import PackError


def cache_root() -> Path:
    override = os.environ.get("AGENT_PACK_CACHE")
    if override:
        return Path(override).expanduser().resolve()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return (base / "agent-pack").resolve()


def source_cache(source: str) -> Path:
    digest = hashlib.sha256(source.encode()).hexdigest()[:16]
    return cache_root() / digest


def run_git(*args: str, cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise PackError("git is required on PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or str(exc)
        raise PackError(f"git {' '.join(args)} failed: {detail}") from exc
    return result.stdout.strip()


def clone(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_git("clone", url, str(dest), cwd=dest.parent)


def repo_basename(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        return name[:-4]
    return name or "repo"


def _safe_ref(ref: str) -> str:
    return ref.replace("/", "__")


def _ensure_bare(source: str) -> Path:
    bare = source_cache(source) / "origin.git"
    if not bare.exists():
        bare.parent.mkdir(parents=True, exist_ok=True)
        run_git("clone", "--bare", source, str(bare), cwd=bare.parent)
        return bare
    run_git("fetch", "--tags", "--force", cwd=bare)
    return bare


def fetch_pack(source: str, tag: str) -> Path:
    bare = _ensure_bare(source)
    dest = source_cache(source) / "tags" / _safe_ref(tag)
    if dest.exists():
        run_git("-c", "advice.detachedHead=false", "checkout", "--detach", tag, cwd=dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_git("worktree", "add", "--detach", str(dest), tag, cwd=bare)
    return dest


def commit_sha(repo: Path, ref: str) -> str:
    return run_git("rev-parse", f"{ref}^{{commit}}", cwd=repo)


def list_tags(repo: Path) -> list[str]:
    raw = run_git("tag", "--sort=-version:refname", cwd=repo)
    return [line for line in raw.splitlines() if line]


def latest_tag(source: str) -> str:
    tags = list_tags(_ensure_bare(source))
    if not tags:
        raise PackError(f"no tags in {source}; pack consumers pin a git tag")
    return tags[0]
