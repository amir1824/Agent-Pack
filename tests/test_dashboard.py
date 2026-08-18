from __future__ import annotations

import io
import json
import threading
from unittest.mock import patch
from urllib.request import urlopen

from agent_pack.cli import main
from agent_pack.dashboard.lifecycle import _pid_alive, kill_dashboard, meta_path, read_meta, start_dashboard
from agent_pack.dashboard.server import make_server
from agent_pack.dashboard.snapshot import build_snapshot
from agent_pack.source import init_pack
from tests.test_cli import PackRepoTest


class DashboardTest(PackRepoTest):
    def test_snapshot_pack_source(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        snap = build_snapshot(pack)
        self.assertEqual(snap["kind"], "pack")
        self.assertEqual(snap["pack"]["errors"], [])
        self.assertIn("example", [item["id"] for item in snap["skills"]])
        self.assertIn("generic-agent", [item["id"] for item in snap["profiles"]])
        self.assertIn("# Constitution", snap["constitution"])

    def test_snapshot_consumer_with_run(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        log = app / ".agents" / "log" / "01ARZ3NDEKTSV4RRFFQ69G5FAV.jsonl"
        log.write_text(
            '{"event":"started","invocation_id":"01ARZ3NDEKTSV4RRFFQ69G5FAV","profile_id":"generic-agent","request_text":"demo","started_at":"2026-08-18T12:00:00Z"}\n'
            '{"event":"completed","invocation_id":"01ARZ3NDEKTSV4RRFFQ69G5FAV","outcome":"done","completed_at":"2026-08-18T12:00:01Z"}\n',
            encoding="utf-8",
        )
        snap = build_snapshot(app)
        self.assertEqual(snap["kind"], "consumer")
        self.assertEqual(snap["runs"][0]["outcome"], "done")
        self.assertTrue(any(item["path"].startswith(".agents/skills/") for item in snap["skills"]))
        self.assertTrue(any(row["path"].startswith(".cursor/skills/") for row in snap["projections"]))

    def test_dashboard_json(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(pack), "dashboard", "--json"]), 0)
            data = json.loads(out.getvalue())
        self.assertEqual(data["kind"], "pack")
        self.assertEqual(data["name"], "fresh")

    def test_api_snapshot(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        server = make_server(pack, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address[:2]
            with urlopen(f"http://{host}:{port}/api/snapshot") as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["kind"], "pack")
            self.assertIn("example", [item["id"] for item in data["skills"]])
            with urlopen(f"http://{host}:{port}/") as resp:
                html = resp.read().decode("utf-8")
            self.assertIn("pack dashboard", html)
            with urlopen(f"http://{host}:{port}/health") as resp:
                self.assertEqual(resp.status, 204)
        finally:
            server.shutdown()
            server.server_close()

    def test_start_reuse_and_kill(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        url = start_dashboard(pack, None, False).strip()
        meta = read_meta(pack)
        self.assertIsNotNone(meta)
        assert meta is not None
        self.assertEqual(url, meta[0])
        with urlopen(f"{url}/health") as resp:
            self.assertEqual(resp.status, 204)
        self.assertEqual(start_dashboard(pack, None, False).strip(), url)
        self.assertEqual(kill_dashboard(pack), "stopped\n")
        self.assertFalse(meta_path(pack).exists())
        self.assertFalse(_pid_alive(meta[2]))
        url2 = start_dashboard(pack, None, False).strip()
        try:
            again = read_meta(pack)
            self.assertIsNotNone(again)
            assert again is not None
            self.assertNotEqual(again[2], meta[2])
            with urlopen(f"{url2}/health") as resp:
                self.assertEqual(resp.status, 204)
        finally:
            kill_dashboard(pack)

    def test_kill_when_not_running(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(pack), "dashboard", "--kill"]), 0)
            self.assertEqual(out.getvalue(), "not running\n")

    def test_neither_pack_nor_lock(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(main(["-C", str(empty), "dashboard", "--json"]), 1)
            self.assertIn("not a pack repo and not bound", err.getvalue())
