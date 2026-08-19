from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from agent_pack.dashboard.snapshot import build_snapshot
from agent_pack.dashboard.upgrade_status import check_upgrade, clear_upgrade_cache
from agent_pack.errors import PackError
from agent_pack.sync import upgrade

STATIC_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
}

# index.html pulls IBM Plex from Google Fonts; everything else must come from us.
CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)


def allowed_hosts(port: int) -> frozenset[str]:
    return frozenset({f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"})


def _static_bytes(name: str) -> bytes:
    return (files("agent_pack.dashboard") / "static" / name).read_bytes()


def _content_length(raw: str | None) -> int | None:
    if raw is None:
        return 0
    try:
        length = int(raw)
    except ValueError:
        return None
    if length < 0:
        return None
    return length


def make_handler(root: Path) -> type[BaseHTTPRequestHandler]:
    resolved = root.resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _host_ok(self) -> bool:
            """Without this, any web page can reach this server via DNS rebinding."""
            bound = self.server.server_address[1]
            return (self.headers.get("Host") or "").strip().lower() in allowed_hosts(bound)

        def do_GET(self) -> None:
            if not self._host_ok():
                self._send(403, "text/plain; charset=utf-8", b"forbidden host\n")
                return
            route = unquote(urlparse(self.path).path)
            if route == "/health":
                self._send(204, "text/plain; charset=utf-8", b"")
                return
            if route == "/api/snapshot":
                try:
                    payload = json.dumps(build_snapshot(resolved)).encode("utf-8")
                except PackError as exc:
                    self._send(400, "application/json", json.dumps({"error": str(exc)}).encode("utf-8"))
                    return
                self._send(200, "application/json", payload)
                return
            if route == "/api/upgrade-status":
                query = parse_qs(urlparse(self.path).query)
                force = query.get("force", [""])[0] in ("1", "true")
                payload = json.dumps(check_upgrade(resolved, force=force)).encode("utf-8")
                self._send(200, "application/json", payload)
                return
            name = "index.html" if route in ("/", "/index.html") else route.lstrip("/")
            ctype = STATIC_TYPES.get(name)
            if ctype is None:
                self._send(404, "text/plain; charset=utf-8", b"not found\n")
                return
            self._send(200, ctype, _static_bytes(name))

        def do_POST(self) -> None:
            if not self._host_ok():
                self._send(403, "text/plain; charset=utf-8", b"forbidden host\n")
                return
            route = unquote(urlparse(self.path).path)
            if route != "/api/upgrade":
                self._send(404, "text/plain; charset=utf-8", b"not found\n")
                return
            length = _content_length(self.headers.get("Content-Length"))
            if length is None:
                self._send(400, "application/json", json.dumps({"error": "invalid Content-Length"}).encode("utf-8"))
                return
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._send(400, "application/json", json.dumps({"error": "invalid json"}).encode("utf-8"))
                return
            tag = body.get("tag")
            upgrade_tag = tag if isinstance(tag, str) and tag.strip() else None
            try:
                lock = upgrade(resolved, upgrade_tag)
                clear_upgrade_cache(resolved)
                payload = json.dumps(
                    {"name": lock.name, "tag": lock.tag, "commit": lock.commit},
                ).encode("utf-8")
            except PackError as exc:
                self._send(400, "application/json", json.dumps({"error": str(exc)}).encode("utf-8"))
                return
            self._send(200, "application/json", payload)

        def _send(self, code: int, ctype: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def make_server(root: Path, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(root))


def serve_forever(root: Path, port: int) -> None:
    make_server(root, port).serve_forever()


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m agent_pack.dashboard.server ROOT PORT")
    serve_forever(Path(sys.argv[1]), int(sys.argv[2]))


if __name__ == "__main__":
    main()
