from __future__ import annotations

import io
import json
import threading
from unittest.mock import patch
from urllib.request import Request, urlopen

from agent_pack.cli import main
from agent_pack.dashboard.lifecycle import _pid_alive, kill_dashboard, meta_path, read_meta, start_dashboard
from agent_pack.dashboard.server import make_server
from agent_pack.dashboard.snapshot import build_snapshot
from agent_pack.log import list_runs
from agent_pack.pack import init_pack
from agent_pack.sync.lockfile import LOCKFILE_NAME
from tests.test_cli import PackRepoTest, _commit_all, _git


class DashboardTest(PackRepoTest):
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
            self.assertIn("agent-pack dashboard", html)
            self.assertIn('class="mark">agent-pack</p>', html)
            self.assertIn('id="view-title"', html)
            with urlopen(f"http://{host}:{port}/app.js") as resp:
                app_js = resp.read().decode("utf-8")
            self.assertNotIn("VIEW_LABELS", app_js)
            self.assertIn("view-title", app_js)
            with urlopen(f"http://{host}:{port}/health") as resp:
                self.assertEqual(resp.status, 204)
        finally:
            server.shutdown()
            server.server_close()

    def test_api_upgrade_status_and_post(self) -> None:
        pack, app = self._bound_app()
        skill = pack / "skills" / "example" / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8").replace(
                "Placeholder skill. Replace with a real team skill or delete this folder.",
                "Placeholder skill v1.1.",
            ),
            encoding="utf-8",
        )
        _commit_all(pack, "feat: v1.1")
        _git(pack, "tag", "v1.1.0")
        server = make_server(app, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address[:2]
            with urlopen(f"http://{host}:{port}/api/upgrade-status?force=1") as resp:
                status = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(status["available"])
            self.assertEqual(status["current_tag"], "v1.0.0")
            self.assertEqual(status["latest_tag"], "v1.1.0")
            req = Request(
                f"http://{host}:{port}/api/upgrade",
                data=json.dumps({"tag": "v1.1.0"}).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urlopen(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(result["tag"], "v1.1.0")
            lock = json.loads((app / LOCKFILE_NAME).read_text(encoding="utf-8"))
            self.assertEqual(lock["tag"], "v1.1.0")
        finally:
            server.shutdown()
            server.server_close()

    def test_api_upgrade_status_pack_only(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        server = make_server(pack, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address[:2]
            with urlopen(f"http://{host}:{port}/api/upgrade-status") as resp:
                status = json.loads(resp.read().decode("utf-8"))
            self.assertIsNone(status)
        finally:
            server.shutdown()
            server.server_close()

    def test_api_upgrade_status_tag_moved(self) -> None:
        pack, app = self._bound_app()
        skill = pack / "skills" / "example" / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8").replace(
                "Write the playbook the agent should follow.",
                "Updated playbook for moved tag.",
            ),
            encoding="utf-8",
        )
        _commit_all(pack, "feat: move v1.0.0")
        _git(pack, "tag", "-f", "v1.0.0")
        server = make_server(app, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address[:2]
            with urlopen(f"http://{host}:{port}/api/upgrade-status?force=1") as resp:
                status = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(status["available"])
            self.assertTrue(status["tag_moved"])
            self.assertEqual(status["current_tag"], "v1.0.0")
            self.assertEqual(status["latest_tag"], "v1.0.0")
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

    def test_pack_source_record_steps_and_json(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(
                main(
                    [
                        "-C",
                        str(pack),
                        "record",
                        "start",
                        "--profile-id",
                        "generic-agent",
                        "--request",
                        "ship the login",
                    ]
                ),
                0,
            )
            invocation_id = out.getvalue().strip()
        self.assertEqual(
            main(
                [
                    "-C",
                    str(pack),
                    "record",
                    "step",
                    "--id",
                    invocation_id,
                    "--name",
                    "charter",
                    "--status",
                    "started",
                ]
            ),
            0,
        )
        self.assertEqual(
            main(
                [
                    "-C",
                    str(pack),
                    "record",
                    "step",
                    "--id",
                    invocation_id,
                    "--name",
                    "charter",
                    "--status",
                    "done",
                ]
            ),
            0,
        )
        self.assertEqual(
            main(
                [
                    "-C",
                    str(pack),
                    "record",
                    "step",
                    "--id",
                    invocation_id,
                    "--name",
                    "specify",
                    "--status",
                    "started",
                ]
            ),
            0,
        )

        runs = list_runs(pack)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].outcome, "open")
        self.assertEqual([step["name"] for step in runs[0].steps], ["charter", "specify"])
        self.assertEqual(runs[0].steps[0]["status"], "done")
        self.assertEqual(runs[0].steps[1]["status"], "started")
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(pack), "dashboard", "--json"]), 0)
            data = json.loads(out.getvalue())
        self.assertEqual(data["runs"][0]["steps"][0]["status"], "done")
        self.assertEqual(data["runs"][0]["steps"][1]["name"], "specify")
        gitignore = (pack / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".agents/log/", gitignore)
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(pack), "log"]), 0)
            self.assertIn("generic-agent", out.getvalue())
        self.assertEqual(
            main(["-C", str(pack), "record", "complete", "--id", invocation_id, "--outcome", "done"]),
            0,
        )
        self.assertEqual(list_runs(pack)[0].outcome, "done")
        with patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(
                main(
                    [
                        "-C",
                        str(pack),
                        "record",
                        "step",
                        "--id",
                        invocation_id,
                        "--name",
                        "late",
                        "--status",
                        "done",
                    ]
                ),
                1,
            )


