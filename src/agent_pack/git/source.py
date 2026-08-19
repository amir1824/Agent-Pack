from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

from agent_pack.errors import PackError

ALLOWED_SCHEMES = ("ssh://", "git://", "https://", "http://", "file://")
SCP_LIKE_RE = re.compile(r"^[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+:(?!/)")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*::?")
USERINFO_RE = re.compile(r"^https?://[^/@]+@", re.IGNORECASE)
REF_RE = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._/+-]*$")
BAD_REF_PARTS = ("..", "~", "^", ":", "?", "*", "[", "\\", "@{")

# Belt and braces behind the scheme allowlist: git must never run a helper for us.
GIT_SAFE_CONFIG = ("-c", "protocol.ext.allow=never", "-c", "protocol.file.allow=user")

_AUTH_HINTS = (
    "permission denied (publickey",
    "could not read username",
    "could not read password",
    "authentication failed",
    "terminal prompts disabled",
    "host key verification failed",
)


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


def validate_source(url: str) -> str:
    """Reject sources git would read as an option, a shell transport, or a secret."""
    source = url.strip()
    if not source:
        raise PackError("source is required")
    if source.startswith("-"):
        raise PackError(f"source must not start with '-': {source!r}")
    if USERINFO_RE.match(source):
        raise PackError(
            "refusing a credential in the source url (it would be written to "
            "agent-pack.lock.json and committed). Use an ssh url such as "
            "git@host:org/repo.git, or plain https and let a git credential helper supply it."
        )
    if source.startswith(ALLOWED_SCHEMES) or SCP_LIKE_RE.match(source):
        return source
    scheme = SCHEME_RE.match(source)
    if scheme:
        raise PackError(
            f"unsupported transport {scheme.group(0)!r}: allowed are "
            f"{', '.join(ALLOWED_SCHEMES)}, scp-like user@host:path, or a local path"
        )
    return source


def validate_ref(ref: str) -> str:
    """Reject refs git would read as an option or resolve to something unintended."""
    tag = ref.strip()
    if not tag:
        raise PackError("tag is required")
    if not REF_RE.fullmatch(tag) or any(part in tag for part in BAD_REF_PARTS) or tag.endswith(".lock"):
        raise PackError(f"invalid tag: {ref!r}")
    return tag


def tag_ref(tag: str) -> str:
    """Fully qualified ref; cannot be parsed as an option and is never ambiguous."""
    return f"refs/tags/{validate_ref(tag)}"


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return env


def _auth_error(detail: str) -> PackError:
    return PackError(
        f"git authentication failed: {detail}\n"
        "  pack does not manage credentials. For a private pack repo use ssh\n"
        "  (git@host:org/repo.git) with a key loaded in ssh-agent, or plain https\n"
        "  with a git credential helper configured."
    )


def run_git(*args: str, cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *GIT_SAFE_CONFIG, *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            env=_git_env(),
        )
    except FileNotFoundError as exc:
        raise PackError("git is required on PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or str(exc)
        if any(hint in detail.lower() for hint in _AUTH_HINTS):
            raise _auth_error(detail) from exc
        raise PackError(f"git {' '.join(args)} failed: {detail}") from exc
    return result.stdout.strip()


def clone(url: str, dest: Path) -> None:
    source = validate_source(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_git("clone", "--", source, str(dest), cwd=dest.parent)


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
        run_git("clone", "--bare", "--", source, str(bare), cwd=bare.parent)
        return bare
    run_git("fetch", "--tags", "--force", cwd=bare)
    return bare


def fetch_pack(source: str, tag: str) -> Path:
    ref = tag_ref(tag)
    bare = _ensure_bare(validate_source(source))
    dest = source_cache(source) / "tags" / _safe_ref(validate_ref(tag))
    if dest.exists():
        run_git("-c", "advice.detachedHead=false", "checkout", "--detach", ref, cwd=dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_git("worktree", "add", "--detach", str(dest), ref, cwd=bare)
    return dest


def commit_sha(repo: Path, ref: str) -> str:
    if ref.startswith("-"):
        raise PackError(f"invalid ref: {ref!r}")
    return run_git("rev-parse", f"{ref}^{{commit}}", cwd=repo)


def list_tags(repo: Path) -> list[str]:
    raw = run_git("tag", "--sort=-version:refname", cwd=repo)
    return [line for line in raw.splitlines() if line]


def latest_tag(source: str) -> str:
    tags = list_tags(_ensure_bare(validate_source(source)))
    if not tags:
        raise PackError(f"no tags in {source}; pack consumers pin a git tag")
    return tags[0]
