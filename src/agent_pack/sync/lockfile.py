from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from agent_pack.errors import PackError

LOCKFILE_NAME = "agent-pack.lock.json"


@dataclass(frozen=True)
class Lockfile:
    name: str
    source: str
    tag: str
    commit: str
    files: Mapping[str, str]

    def to_json(self) -> str:
        payload = {
            "name": self.name,
            "source": self.source,
            "tag": self.tag,
            "commit": self.commit,
            "files": dict(sorted(self.files.items())),
        }
        return json.dumps(payload, indent=2) + "\n"


def lockfile_path(app_root: Path) -> Path:
    return app_root / LOCKFILE_NAME


def read_lockfile(app_root: Path) -> Lockfile:
    path = lockfile_path(app_root)
    if not path.is_file():
        raise PackError(f"no {LOCKFILE_NAME}; run pack bind first")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PackError(f"invalid lockfile: {exc}") from exc
    if not isinstance(data, dict):
        raise PackError("invalid lockfile: expected an object")
    files = data.get("files") or {}
    if not isinstance(files, dict):
        raise PackError("invalid lockfile: files must be an object")
    required = ("name", "source", "tag", "commit")
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise PackError(f"invalid lockfile: missing {', '.join(missing)}")
    return Lockfile(
        name=str(data["name"]),
        source=str(data["source"]),
        tag=str(data["tag"]),
        commit=str(data["commit"]),
        files={str(path_key): str(digest) for path_key, digest in files.items()},
    )


def write_lockfile(app_root: Path, lock: Lockfile) -> None:
    lockfile_path(app_root).write_text(lock.to_json(), encoding="utf-8")
