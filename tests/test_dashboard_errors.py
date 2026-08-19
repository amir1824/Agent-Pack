from __future__ import annotations

import io
import json
from unittest.mock import patch

from agent_pack.cli import main
from agent_pack.dashboard.snapshot import build_snapshot
from agent_pack.pack import init_pack
from tests.test_cli import PackRepoTest


class DashboardErrorsTest(PackRepoTest):
    def test_snapshot_pack_source(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        snap = build_snapshot(pack)
        self.assertEqual(snap["kind"], "pack")
        self.assertEqual(snap["pack"]["errors"], [])
        self.assertIn("example", [item["id"] for item in snap["skills"]])
        self.assertIn("generic-agent", [item["id"] for item in snap["profiles"]])
        self.assertIn("# Constitution", snap["constitution"])

    def test_kill_when_not_running(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(pack), "dashboard", "--kill"]), 0)
            self.assertEqual(out.getvalue(), "not running\n")

    def test_dashboard_json(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(pack), "dashboard", "--json"]), 0)
            data = json.loads(out.getvalue())
        self.assertEqual(data["kind"], "pack")
        self.assertEqual(data["name"], "fresh")

    def test_neither_pack_nor_lock(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(main(["-C", str(empty), "dashboard", "--json"]), 1)
            self.assertIn("not a pack repo and not bound", err.getvalue())
        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(
                main(["-C", str(empty), "record", "start", "--profile-id", "x", "--request", "y"]),
                1,
            )
            self.assertIn("not a pack repo and not bound", err.getvalue())


class DashboardHttpGuardTest(PackRepoTest):
    def _serve(self):
        import threading

        from agent_pack.dashboard.server import make_server

        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        server = make_server(pack, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def _get(self, port: int, path: str, host: str | None = None):
        from http.client import HTTPConnection

        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", path, headers={"Host": host} if host else {})
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), resp.read()
        finally:
            conn.close()

    def test_rejects_foreign_host_header(self) -> None:
        # DNS rebinding: a page on any origin resolves its name to 127.0.0.1 and reads the snapshot.
        port = self._serve()
        for host in ("evil.com", f"evil.com:{port}", "pack.attacker.test"):
            with self.subTest(host=host):
                status, _headers, _body = self._get(port, "/api/snapshot", host)
                self.assertEqual(status, 403)

    def test_allows_loopback_hosts(self) -> None:
        port = self._serve()
        for host in (f"127.0.0.1:{port}", f"localhost:{port}"):
            with self.subTest(host=host):
                status, _headers, body = self._get(port, "/api/snapshot", host)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body.decode("utf-8"))["kind"], "pack")

    def test_security_headers(self) -> None:
        port = self._serve()
        status, headers, _body = self._get(port, "/", f"127.0.0.1:{port}")
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        csp = headers["Content-Security-Policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
