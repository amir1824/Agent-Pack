from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_pack.consumer import bind, diff, format_status, status, sync, upgrade
from agent_pack.dashboard.lifecycle import kill_dashboard, start_dashboard
from agent_pack.dashboard.snapshot import build_snapshot
from agent_pack.errors import CheckFailed, PackError
from agent_pack.log import OUTCOMES, format_log, record_complete, record_start
from agent_pack.source import init_pack
from agent_pack.target import resolve_target
from agent_pack.validate import validate_pack


def _take_globals(argv: list[str]) -> tuple[str | None, str | None, list[str]]:
    directory: str | None = None
    repo: str | None = None
    rest: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "-C":
            if index + 1 >= len(argv):
                raise PackError("-C requires a directory")
            directory = argv[index + 1]
            index += 2
            continue
        if arg == "--repo":
            if index + 1 >= len(argv):
                raise PackError("--repo requires a git url")
            repo = argv[index + 1]
            index += 2
            continue
        if arg.startswith("--repo="):
            repo = arg.split("=", 1)[1]
            index += 1
            continue
        rest.append(arg)
        index += 1
    return directory, repo, rest


def _port(value: str) -> int:
    port = int(value)
    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError("port must be 1-65535")
    return port


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pack",
        description="Bind one agent-pack git repo to an app and sync md/yaml files.",
    )
    parser.add_argument("-C", dest="directory", default=None, help="existing app or pack checkout")
    parser.add_argument("--repo", dest="repo", default=None, help="clone this app git url, then run there")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="scaffold a pack repo")
    init_p.add_argument("--name", dest="pack_name", help="pack.yaml name (default: directory name)")

    sub.add_parser("validate", help="validate pack frontmatter, ids, and no symlinks")

    bind_p = sub.add_parser("bind", help="point this app at a pack git url + tag")
    bind_p.add_argument("git_url", help="pack repository url or local path")
    bind_p.add_argument("--name", default="pack", help="lockfile name (default: pack)")
    bind_p.add_argument("--tag", default=None, help="pack tag to pin (default: latest tag)")

    sub.add_parser("sync", help="copy pack into .agents/ and host Cursor/Claude paths")
    sub.add_parser("status", help="show name, url, tag, dirty vs lock")
    sub.add_parser("check", help="status, exit 1 if dirty or not synced")
    sub.add_parser("diff", help="diff .agents/ against the locked tag")

    up = sub.add_parser("upgrade", help="move the pinned tag and sync")
    up.add_argument("--tag", default=None, help="tag to move to (default: latest tag)")

    log_p = sub.add_parser("log", help="print the run log table")
    log_p.add_argument("-n", "--limit", type=int, default=20, help="max rows (default: 20)")

    record_p = sub.add_parser("record", help="write a run-log event")
    record_sub = record_p.add_subparsers(dest="record_command", required=True)
    start_p = record_sub.add_parser("start", help="write a started event")
    start_p.add_argument("--profile-id", required=True, help="profile that is running")
    start_p.add_argument("--request", required=True, help="request text")
    complete_p = record_sub.add_parser("complete", help="write a completed event")
    complete_p.add_argument("--id", dest="invocation_id", required=True, help="id from pack record start")
    complete_p.add_argument(
        "--outcome",
        required=True,
        choices=OUTCOMES,
        help="run outcome",
    )

    dash = sub.add_parser("dashboard", help="open the local pack dashboard")
    dash.add_argument("--port", type=_port, default=None, help="preferred port (default: 8765, then next free)")
    dash.add_argument("--open", action="store_true", help="open the URL in a browser")
    dash.add_argument("--kill", action="store_true", help="stop the dashboard for this checkout")
    dash.add_argument("--json", action="store_true", dest="as_json", help="print snapshot JSON and exit")
    return parser


def _run(args: argparse.Namespace) -> str:
    target = resolve_target(args.directory, args.repo, create=args.command == "init")
    root = target.root
    command = args.command
    handlers = {
        "init": lambda: _init(root, args.pack_name),
        "validate": lambda: _validate(root),
        "bind": lambda: _bind(root, args),
        "sync": lambda: _sync(root),
        "status": lambda: format_status(status(root)),
        "check": lambda: _check(root),
        "diff": lambda: diff(root),
        "upgrade": lambda: _upgrade(root, args.tag),
        "log": lambda: format_log(root, args.limit),
        "record": lambda: _record(root, args),
        "dashboard": lambda: _dashboard(root, args),
    }
    handler = handlers.get(command)
    if handler is None:
        raise PackError(f"unknown command: {command}")
    return handler()


def _init(root: Path, pack_name: str | None) -> str:
    name = pack_name or root.name
    init_pack(root, name)
    return f"initialized pack {name} in {root}\n"


def _validate(root: Path) -> str:
    errors = validate_pack(root)
    if errors:
        raise PackError("validate failed:\n" + "\n".join(f"  {item}" for item in errors))
    return "ok\n"


def _bind(root: Path, args: argparse.Namespace) -> str:
    lock = bind(root, args.git_url, args.name, args.tag)
    return f"bound {lock.name} -> {lock.source}@{lock.tag} ({lock.commit[:12]})\n"


def _sync(root: Path) -> str:
    lock = sync(root)
    return f"synced {lock.name}@{lock.tag} ({len(lock.files)} files)\n"


def _upgrade(root: Path, tag: str | None) -> str:
    lock = upgrade(root, tag)
    return f"upgraded {lock.name} -> {lock.tag} ({lock.commit[:12]})\n"


def _check(root: Path) -> str:
    report = status(root)
    text = format_status(report)
    if report.dirty:
        raise CheckFailed(text)
    return text


def _record(root: Path, args: argparse.Namespace) -> str:
    if args.record_command == "start":
        return record_start(root, args.profile_id, args.request)
    return record_complete(root, args.invocation_id, args.outcome)


def _dashboard(root: Path, args: argparse.Namespace) -> str:
    if args.kill:
        return kill_dashboard(root)
    if args.as_json:
        return json.dumps(build_snapshot(root), indent=2) + "\n"
    return start_dashboard(root, args.port, args.open)


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    try:
        directory, repo, rest = _take_globals(raw)
        args = parser.parse_args(rest)
        args.directory = directory
        args.repo = repo
        sys.stdout.write(_run(args))
    except CheckFailed as exc:
        sys.stdout.write(exc.report)
        return 1
    except PackError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    return 0
