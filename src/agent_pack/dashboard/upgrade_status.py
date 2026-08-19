from __future__ import annotations

import time
from pathlib import Path

from agent_pack.errors import PackError
from agent_pack.git import commit_sha, fetch_pack, latest_tag
from agent_pack.sync.lockfile import lockfile_path, read_lockfile

CACHE_TTL_SEC = 300
# ponytail: in-process dict only; concurrent checks may duplicate git fetch; no cross-process invalidation — add a lock or shared cache if this becomes hot.
_cache: dict[str, tuple[float, dict[str, object]]] = {}


def clear_upgrade_cache(root: Path | None = None) -> None:
    if root is None:
        _cache.clear()
        return
    _cache.pop(str(root.resolve()), None)


def check_upgrade(root: Path, *, force: bool = False) -> dict[str, object] | None:
    root = root.resolve()
    if not lockfile_path(root).is_file():
        return None
    key = str(root)
    now = time.monotonic()
    if not force and key in _cache and now - _cache[key][0] < CACHE_TTL_SEC:
        return _cache[key][1]

    lock = read_lockfile(root)
    try:
        latest = latest_tag(lock.source)
        checkout = fetch_pack(lock.source, lock.tag)
        remote_commit = commit_sha(checkout, "HEAD")
        tag_moved = remote_commit != lock.commit
        available = latest != lock.tag or tag_moved
        result: dict[str, object] = {
            "available": available,
            "current_tag": lock.tag,
            "latest_tag": latest,
            "tag_moved": tag_moved,
        }
    except PackError as exc:
        result = {
            "available": False,
            "current_tag": lock.tag,
            "latest_tag": lock.tag,
            "tag_moved": False,
            "error": str(exc),
        }
    _cache[key] = (now, result)
    return result
