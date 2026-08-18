from __future__ import annotations

import difflib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from agent_pack.adapters import install_projections, upsert_root_agents_md
from agent_pack.errors import PackError
from agent_pack.gitutil import commit_sha, fetch_pack, latest_tag
from agent_pack.lockfile import Lockfile, lockfile_path, read_lockfile, write_lockfile
from agent_pack.log import ensure_log_scaffold
from agent_pack.source import consumer_rel, iter_pack_files, sha256_file
from agent_pack.validate import require_valid_pack

AGENTS_DIR = ".agents"
GITIGNORE_RULE = ".agents/log/"


def _normalize_source(url: str) -> str:
    path = Path(url).expanduser()
    if path.exists():
        return str(path.resolve())
    return url


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


def ensure_gitignore(app_root: Path, rule: str = GITIGNORE_RULE) -> None:
    path = app_root / ".gitignore"
    if not path.exists():
        path.write_text(rule + "\n", encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    existing = {line.strip() for line in text.splitlines()}
    if rule in existing or rule.rstrip("/") in existing:
        return
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + rule + "\n", encoding="utf-8")


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


def sync(app_root: Path, tag: str | None = None) -> Lockfile:
    lock = read_lockfile(app_root)
    resolved_tag = tag or lock.tag
    checkout = fetch_pack(lock.source, resolved_tag)
    require_valid_pack(checkout)
    sha = commit_sha(checkout, "HEAD")
    copied: dict[str, str] = {}
    for src in iter_pack_files(checkout):
        rel = consumer_rel(src, checkout)
        dest = app_root / rel
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
        return bool(self.modified or self.missing or self.extra or not self.synced)


def _agents_tracked_files(app_root: Path) -> set[str]:
    agents = app_root / AGENTS_DIR
    if not agents.is_dir():
        return set()
    return {
        path.relative_to(app_root).as_posix()
        for path in agents.rglob("*")
        if path.is_file() and not path.relative_to(app_root).as_posix().startswith(".agents/log/")
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
    if not report.dirty:
        lines.append("state: clean")
        return "\n".join(lines) + "\n"
    lines.append("state: dirty")
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
    chunks: list[str] = []
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
    if not chunks:
        return "no differences\n"
    return "".join(chunks)


def upgrade(app_root: Path, tag: str | None) -> Lockfile:
    lock = read_lockfile(app_root)
    return sync(app_root, tag or latest_tag(lock.source))
