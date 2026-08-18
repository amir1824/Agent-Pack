from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import unquote, urlparse

from agent_pack.dashboard.snapshot import build_snapshot
from agent_pack.errors import PackError

STATIC_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
}


def _static_bytes(name: str) -> bytes:
    return (files("agent_pack.dashboard") / "static" / name).read_bytes()


def make_handler(root: Path) -> type[BaseHTTPRequestHandler]:
    resolved = root.resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
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
            name = "index.html" if route in ("/", "/index.html") else route.lstrip("/")
            ctype = STATIC_TYPES.get(name)
            if ctype is None:
                self._send(404, "text/plain; charset=utf-8", b"not found\n")
                return
            self._send(200, ctype, _static_bytes(name))

        def _send(self, code: int, ctype: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
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
