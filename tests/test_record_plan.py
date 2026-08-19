from __future__ import annotations

import io
import json
from unittest.mock import patch

from agent_pack.cli import main
from agent_pack.log import list_runs
from agent_pack.pack import init_pack
from tests.test_cli import PackRepoTest


class RecordPlanTest(PackRepoTest):
    def test_plan_step_logs_and_events(self) -> None:
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
                        "ship login",
                        "--plan",
                        "product,designer,qa",
                    ]
                ),
                0,
            )
            invocation_id = out.getvalue().strip()
        run = list_runs(pack)[0]
        self.assertEqual(list(run.plan), ["product", "designer", "qa"])
        self.assertEqual(run.steps, ())
        self.assertEqual(len(run.events), 1)
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
                    "product",
                    "--status",
                    "started",
                    "--detail",
                    "PRD draft",
                ]
            ),
            0,
        )
        self.assertEqual(len(list_runs(pack)[0].events), 1)
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
                    "product",
                    "--status",
                    "done",
                    "--detail",
                    "scope locked",
                ]
            ),
            0,
        )
        finished_step = list_runs(pack)[0].steps[0]
        self.assertEqual(finished_step["status"], "done")
        self.assertEqual(len(finished_step["log"]), 2)
        # designer/qa never ran — completing as done is blocked unless forced
        # (see test_plan_enforcement.py for the dedicated enforcement tests).
        with patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(
                main(["-C", str(pack), "record", "complete", "--id", invocation_id, "--outcome", "done"]),
                1,
            )
        self.assertEqual(
            main(
                ["-C", str(pack), "record", "complete", "--id", invocation_id, "--outcome", "done", "--force"]
            ),
            0,
        )
        self.assertEqual(len(list_runs(pack)[0].events), 2)
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
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(pack), "dashboard", "--json"]), 0)
            snap = json.loads(out.getvalue())
        self.assertEqual(snap["runs"][0]["plan"], ["product", "designer", "qa"])

    def test_plan_dedupe(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        with patch("sys.stdout", new=io.StringIO()):
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
                        "dup",
                        "--plan",
                        "product,product,qa",
                    ]
                ),
                0,
            )
        self.assertEqual(list(list_runs(pack)[0].plan), ["product", "qa"])
