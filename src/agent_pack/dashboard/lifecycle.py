from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import NoReturn
from urllib.error import URLError
from urllib.request import urlopen

from agent_pack.sync import ensure_gitignore
from agent_pack.dashboard.snapshot import build_snapshot
from agent_pack.errors import PackError

META_NAME = ".pack-dashboard"
GITIGNORE_RULE = ".pack-dashboard"
DEFAULT_PORT = 8765
HOST = "127.0.0.1"


def meta_path(root: Path) -> Path:
    return root / META_NAME


def dashboard_url(port: int) -> str:
    return f"http://{HOST}:{port}"


def _can_bind(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((HOST, port))
        except OSError:
            return False
    return True


def find_free_port(start: int = DEFAULT_PORT, attempts: int = 50) -> int:
    if start < 1 or start > 65535:
        raise PackError(f"port must be 1-65535, got {start}")
    port = next((candidate for candidate in range(start, min(start + attempts, 65536)) if _can_bind(candidate)), None)
    if port is None:
        raise PackError(f"no free port in {start}-{min(start + attempts, 65536) - 1}")
    return port


def read_meta(root: Path) -> tuple[str, int, int] | None:
    path = meta_path(root)
    if not path.is_file():
        return None
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 3:
        return None
    try:
        return lines[0], int(lines[1]), int(lines[2])
    except ValueError:
        return None


def write_meta(root: Path, url: str, port: int, pid: int) -> None:
    meta_path(root).write_text(f"{url}\n{port}\n{pid}\n", encoding="utf-8")


def _cmdline(pid: int) -> str:
    try:
        return subprocess.check_output(
            ["ps", "-ww", "-p", str(pid), "-o", "command="],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _ours(pid: int, root: Path) -> bool:
    if pid <= 1:
        return False
    cmd = _cmdline(pid)
    return "agent_pack.dashboard.server" in cmd and str(root.resolve()) in cmd


def _pid_alive(pid: int) -> bool:
    try:
        waited, _status = os.waitpid(pid, os.WNOHANG)
        if waited == pid:
            return False
    except ChildProcessError:
        pass
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _healthy(url: str) -> bool:
    try:
        with urlopen(f"{url}/health", timeout=0.4) as resp:
            return 200 <= resp.status < 300
    except (URLError, OSError, TimeoutError):
        return False


def _stop_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(40):
        if not _pid_alive(pid):
            return
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return
    for _ in range(20):
        if not _pid_alive(pid):
            return
        time.sleep(0.05)


def _clear_stale(root: Path) -> None:
    meta = read_meta(root)
    if meta is None:
        meta_path(root).unlink(missing_ok=True)
        return
    _url, _port, pid = meta
    if _ours(pid, root) and _pid_alive(pid):
        _stop_pid(pid)
    meta_path(root).unlink(missing_ok=True)


def running(root: Path) -> tuple[str, int, int] | None:
    meta = read_meta(root)
    if meta is None:
        return None
    url, _port, pid = meta
    if _ours(pid, root) and _pid_alive(pid) and _healthy(url):
        return meta
    return None


def kill_dashboard(root: Path) -> str:
    meta = read_meta(root)
    if meta is None:
        meta_path(root).unlink(missing_ok=True)
        return "not running\n"
    _url, _port, pid = meta
    if _ours(pid, root) and _pid_alive(pid):
        _stop_pid(pid)
    meta_path(root).unlink(missing_ok=True)
    return "stopped\n"


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    src = str(Path(__file__).resolve().parents[2])
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(part for part in (src, current) if part)
    return env


def _spawn(root: Path, port: int) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-m", "agent_pack.dashboard.server", str(root.resolve()), str(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=_child_env(),
    )


def _fail_start(proc: subprocess.Popen[bytes]) -> NoReturn:
    proc.kill()
    raise PackError("dashboard failed to start")


def start_dashboard(root: Path, port: int | None, open_browser: bool) -> str:
    build_snapshot(root)
    existing = running(root)
    if existing is not None:
        url, _port, _pid = existing
        if open_browser:
            webbrowser.open(url)
        return f"{url}\n"
    _clear_stale(root)
    chosen = find_free_port(port or DEFAULT_PORT)
    url = dashboard_url(chosen)
    ensure_gitignore(root, GITIGNORE_RULE)
    proc = _spawn(root, chosen)
    # ponytail: 2s poll is enough; upgrade to a ready event if startup grows past a subprocess.
    for _ in range(40):
        if _healthy(url):
            write_meta(root, url, chosen, proc.pid)
            if open_browser:
                webbrowser.open(url)
            return f"{url}\n"
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    _fail_start(proc)
