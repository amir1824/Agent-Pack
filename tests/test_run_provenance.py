from __future__ import annotations

import io
import json
from unittest.mock import patch

from agent_pack.cli import main
from agent_pack.log import list_runs
from agent_pack.pack import init_pack
from tests.test_cli import PackRepoTest, _commit_all, _git


class RunProvenanceTest(PackRepoTest):
    def test_started_event_carries_the_pin(self) -> None:
        _pack, app = self._bound_app()

        with patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(
                main(
                    ["-C", str(app), "record", "start", "--profile-id", "generic-agent", "--request", "x"]
                ),
                0,
            )
        run = list_runs(app)[0]
        self.assertEqual(run.pack_name, "pack")
        self.assertEqual(run.pack_tag, "v1.0.0")
        self.assertTrue(run.pack_commit)

    def test_two_runs_under_different_pins_carry_different_commits(self) -> None:
        pack, app = self._bound_app()

        with patch("sys.stdout", new=io.StringIO()) as out:
            main(["-C", str(app), "record", "start", "--profile-id", "generic-agent", "--request", "first"])
            first_id = out.getvalue().strip()
        first_commit = list_runs(app)[0].pack_commit

        (pack / "AGENTS.md").write_text("# App agents\nupdated.\n", encoding="utf-8")
        _commit_all(pack, "docs: tweak")
        _git(pack, "tag", "v1.1.0")
        with patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(main(["-C", str(app), "upgrade", "--tag", "v1.1.0"]), 0)
            main(["-C", str(app), "record", "start", "--profile-id", "generic-agent", "--request", "second"])

        runs = {run.request_text: run for run in list_runs(app)}
        self.assertEqual(runs["first"].pack_tag, "v1.0.0")
        self.assertEqual(runs["first"].pack_commit, first_commit)
        self.assertEqual(runs["second"].pack_tag, "v1.1.0")
        self.assertNotEqual(runs["second"].pack_commit, first_commit)

    def test_pack_repo_only_run_has_no_pin(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        with patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(
                main(
                    ["-C", str(pack), "record", "start", "--profile-id", "generic-agent", "--request", "x"]
                ),
                0,
            )
        run = list_runs(pack)[0]
        self.assertIsNone(run.pack_name)
        self.assertIsNone(run.pack_tag)
        self.assertIsNone(run.pack_commit)

    def test_dashboard_snapshot_surfaces_the_pin(self) -> None:
        _pack, app = self._bound_app()
        with patch("sys.stdout", new=io.StringIO()):
            main(["-C", str(app), "record", "start", "--profile-id", "generic-agent", "--request", "x"])
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "dashboard", "--json"]), 0)
            snap = json.loads(out.getvalue())
        self.assertEqual(snap["runs"][0]["pack_tag"], "v1.0.0")


class LogExportTest(PackRepoTest):
    def test_export_round_trips_every_run(self) -> None:
        _pack, app = self._bound_app()
        with patch("sys.stdout", new=io.StringIO()):
            main(["-C", str(app), "record", "start", "--profile-id", "generic-agent", "--request", "one"])
            main(["-C", str(app), "record", "start", "--profile-id", "generic-agent", "--request", "two"])

        export_path = self.root / "runs.json"
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "log", "--export", str(export_path)]), 0)
            self.assertIn("exported 2 run(s)", out.getvalue())

        exported = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual(len(exported), 2)
        self.assertEqual({run["request_text"] for run in exported}, {"one", "two"})
        self.assertEqual(exported[0]["pack_tag"], "v1.0.0")

    def test_export_with_no_runs_is_an_empty_array(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        export_path = self.root / "runs.json"
        with patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(main(["-C", str(pack), "log", "--export", str(export_path)]), 0)
        self.assertEqual(json.loads(export_path.read_text(encoding="utf-8")), [])
