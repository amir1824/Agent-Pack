from __future__ import annotations

import difflib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from agent_pack.errors import PackError
from agent_pack.git import commit_sha, fetch_pack, latest_tag, validate_source
from agent_pack.log.scaffold import ensure_log_scaffold
from agent_pack.pack import consumer_rel, iter_pack_files, require_valid_pack, safe_dest, sha256_file
from agent_pack.sync.adapters import install_projections, upsert_root_agents_md
from agent_pack.sync.gitignore import GITIGNORE_RULE, ensure_gitignore
from agent_pack.sync.lockfile import Lockfile, lockfile_path, read_lockfile, write_lockfile

AGENTS_DIR = ".agents"


def _normalize_source(url: str) -> str:
    path = Path(url).expanduser()
    if path.exists():
        return str(path.resolve())
    return validate_source(url)


def _copy_file(src: Path, dest: Path) -> None:
    if src.is_symlink():
        raise PackError(f"refusing to copy symlink: {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.packtmp")
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def bind(app_root: Path, git_url: str, name: str, tag: str | None) -> Lockfile:
    if lockfile_path(app_root).exists():
        raise PackError("already bound; use pack upgrade to move the tag")
    source = _normalize_source(git_url)
    resolved_tag = tag or latest_tag(source)
    checkout = fetch_pack(source, resolved_tag)
    require_valid_pack(checkout)
    lock = Lockfile(
        name=name,
        source=source,
        tag=resolved_tag,
        commit=commit_sha(checkout, "HEAD"),
        files={},
    )
    write_lockfile(app_root, lock)
    ensure_gitignore(app_root)
    return lock


def _require_stable_pin(lock: Lockfile, resolved_tag: str, sha: str) -> None:
    """Git tags are mutable. A moved tag silently swaps agent instructions, so refuse it."""
    if resolved_tag != lock.tag or not lock.commit or sha == lock.commit:
        return
    raise PackError(
        f"pinned tag {lock.tag} moved: lockfile has {lock.commit[:12]}, "
        f"{lock.source} now resolves to {sha[:12]}.\n"
        "  Nothing was copied. Inspect with pack diff, then accept with\n"
        f"  pack upgrade --tag {lock.tag}  (or pack sync --allow-tag-move)"
    )


def sync(app_root: Path, tag: str | None = None, *, allow_tag_move: bool = False) -> Lockfile:
    lock = read_lockfile(app_root)
    resolved_tag = tag or lock.tag
    checkout = fetch_pack(lock.source, resolved_tag)
    require_valid_pack(checkout)
    sha = commit_sha(checkout, "HEAD")
    if not allow_tag_move:
        _require_stable_pin(lock, resolved_tag, sha)
    copied: dict[str, str] = {}
    for src in iter_pack_files(checkout):
        rel = consumer_rel(src, checkout)
        dest = safe_dest(app_root, rel)
        _copy_file(src, dest)
        copied[rel] = sha256_file(dest)
        copied.update(install_projections(app_root, rel, dest))
    stale = set(lock.files) - set(copied)
    for rel in stale:
        path = app_root / rel
        if path.is_file() or path.is_symlink():
            path.unlink()
    new_lock = Lockfile(
        name=lock.name,
        source=lock.source,
        tag=resolved_tag,
        commit=sha,
        files=copied,
    )
    upsert_root_agents_md(app_root, new_lock)
    write_lockfile(app_root, new_lock)
    ensure_gitignore(app_root)
    ensure_log_scaffold(app_root)
    return new_lock


@dataclass(frozen=True)
class Status:
    lock: Lockfile
    synced: bool
    modified: tuple[str, ...]
    missing: tuple[str, ...]
    extra: tuple[str, ...]

    @property
    def dirty(self) -> bool:
        # `extra` is content the consumer added on top of the pack (their own skills,
        # host-only files, etc). That is the point of an app repo, not drift — so it
        # does not fail `pack check`. Only a changed or missing pack-managed file does.
        return bool(self.modified or self.missing or not self.synced)


def _agents_tracked_files(app_root: Path) -> set[str]:
    agents = app_root / AGENTS_DIR
    if not agents.is_dir():
        return set()
    ignore_prefix = GITIGNORE_RULE.rstrip("/") + "/"
    return {
        path.relative_to(app_root).as_posix()
        for path in agents.rglob("*")
        if path.is_file() and not path.relative_to(app_root).as_posix().startswith(ignore_prefix)
    }


def status(app_root: Path) -> Status:
    lock = read_lockfile(app_root)
    if not lock.files:
        return Status(lock=lock, synced=False, modified=(), missing=(), extra=())
    present = _agents_tracked_files(app_root)
    managed = set(lock.files)
    missing = tuple(sorted(rel for rel in managed if not (app_root / rel).is_file()))
    modified = tuple(
        sorted(
            rel
            for rel in managed
            if (app_root / rel).is_file() and sha256_file(app_root / rel) != lock.files[rel]
        )
    )
    extra = tuple(sorted(present - managed))
    return Status(lock=lock, synced=True, modified=modified, missing=missing, extra=extra)


def format_status(report: Status) -> str:
    lock = report.lock
    lines = [
        f"name: {lock.name}",
        f"source: {lock.source}",
        f"tag: {lock.tag}",
        f"commit: {lock.commit}",
    ]
    if not report.synced:
        lines.append("state: not synced")
        return "\n".join(lines) + "\n"
    lines.append("state: dirty" if report.dirty else "state: clean")
    for rel in report.modified:
        lines.append(f"  modified: {rel}")
    for rel in report.missing:
        lines.append(f"  missing: {rel}")
    for rel in report.extra:
        lines.append(f"  extra: {rel}")
    return "\n".join(lines) + "\n"


def diff(app_root: Path) -> str:
    lock = read_lockfile(app_root)
    checkout = fetch_pack(lock.source, lock.tag)
    require_valid_pack(checkout)
    sha = commit_sha(checkout, "HEAD")
    chunks: list[str] = []
    if lock.commit and sha != lock.commit:
        chunks.append(
            f"# warning: tag {lock.tag} moved {lock.commit[:12]} -> {sha[:12]}; "
            "diffing against the new commit\n"
        )
    pack_files = {consumer_rel(src, checkout): src for src in iter_pack_files(checkout)}
    local_files = _agents_tracked_files(app_root)
    names = sorted(set(pack_files) | local_files)
    for rel in names:
        src = pack_files.get(rel)
        dest = app_root / rel
        left = src.read_text(encoding="utf-8").splitlines(keepends=True) if src and src.is_file() else []
        right = dest.read_text(encoding="utf-8").splitlines(keepends=True) if dest.is_file() else []
        if left == right:
            continue
        from_file = f"a/{rel}" if src else "/dev/null"
        to_file = f"b/{rel}" if dest.is_file() else "/dev/null"
        rendered = difflib.unified_diff(left, right, fromfile=from_file, tofile=to_file)
        chunks.append("".join(rendered))
    if len(chunks) == (1 if lock.commit and sha != lock.commit else 0):
        return "".join(chunks) + "no differences\n"
    return "".join(chunks)


def upgrade(app_root: Path, tag: str | None) -> Lockfile:
    lock = read_lockfile(app_root)
    return sync(app_root, tag or latest_tag(lock.source), allow_tag_move=True)
