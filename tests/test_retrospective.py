from __future__ import annotations

import io
import json
from unittest.mock import patch

from agent_pack.cli import main
from agent_pack.log import list_runs
from tests.test_cli import PackRepoTest


class AgentLogTest(PackRepoTest):
    def _run_with_steps(self, app, request_text, plan, done):
        with patch("sys.stdout", new=io.StringIO()) as out:
            main(
                [
                    "-C",
                    str(app),
                    "record",
                    "start",
                    "--profile-id",
                    "generic-agent",
                    "--request",
                    request_text,
                    "--plan",
                    ",".join(plan),
                ]
            )
            invocation_id = out.getvalue().strip()
        with patch("sys.stdout", new=io.StringIO()):
            for name in done:
                main(
                    [
                        "-C",
                        str(app),
                        "record",
                        "step",
                        "--id",
                        invocation_id,
                        "--name",
                        name,
                        "--status",
                        "started",
                    ]
                )
                main(
                    [
                        "-C",
                        str(app),
                        "record",
                        "step",
                        "--id",
                        invocation_id,
                        "--name",
                        name,
                        "--status",
                        "done",
                        "--detail",
                        f"{name} done in {request_text}",
                    ]
                )
        return invocation_id

    def test_agent_log_spans_multiple_runs(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)

        self._run_with_steps(app, "first", ["product", "qa"], ["product", "qa"])
        self._run_with_steps(app, "second", ["product", "qa"], ["product", "qa"])

        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "log", "--agent", "qa"]), 0)
            table = out.getvalue()
        self.assertIn("first", table)
        self.assertIn("second", table)
        self.assertNotIn("does-not-exist", table)

    def test_agent_log_export_is_flat_and_agent_scoped(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        self._run_with_steps(app, "first", ["product", "qa"], ["product", "qa"])

        export_path = self.root / "qa.json"
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "log", "--agent", "qa", "--export", str(export_path)]), 0)
            self.assertIn("exported 1 step(s)", out.getvalue())
        entries = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["status"], "done")
        self.assertIn("qa done in first", entries[0]["detail"])
        self.assertEqual(entries[0]["pack_tag"], "v1.0.0")

    def test_agent_with_no_history_is_reported_not_an_error(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "log", "--agent", "nobody"]), 0)
            self.assertIn("no steps recorded", out.getvalue())


class FromRunTest(PackRepoTest):
    def test_plan_derives_from_the_actual_participants_of_a_prior_run(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)

        # the original delivery run only actually used product + qa,
        # even though its plan could in principle have named more roles
        with patch("sys.stdout", new=io.StringIO()) as out:
            main(
                [
                    "-C",
                    str(app),
                    "record",
                    "start",
                    "--profile-id",
                    "generic-agent",
                    "--request",
                    "checkout flow",
                    "--plan",
                    "product,qa",
                ]
            )
            original_id = out.getvalue().strip()
        with patch("sys.stdout", new=io.StringIO()):
            for name in ("product", "qa"):
                main(["-C", str(app), "record", "step", "--id", original_id, "--name", name, "--status", "done"])
            main(["-C", str(app), "record", "complete", "--id", original_id, "--outcome", "done"])

        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(
                main(
                    [
                        "-C",
                        str(app),
                        "record",
                        "start",
                        "--profile-id",
                        "retrospective",
                        "--request",
                        f"retro on {original_id}",
                        "--from-run",
                        original_id,
                    ]
                ),
                0,
            )
            retro_id = out.getvalue().strip()

        retro_run = next(run for run in list_runs(app) if run.invocation_id == retro_id)
        self.assertEqual(list(retro_run.plan), ["product", "qa"])
        self.assertEqual(retro_run.from_run, original_id)

    def test_explicit_plan_still_wins_over_from_run(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        with patch("sys.stdout", new=io.StringIO()) as out:
            main(
                [
                    "-C",
                    str(app),
                    "record",
                    "start",
                    "--profile-id",
                    "generic-agent",
                    "--request",
                    "x",
                    "--plan",
                    "product",
                ]
            )
            original_id = out.getvalue().strip()

        with patch("sys.stdout", new=io.StringIO()) as out:
            main(
                [
                    "-C",
                    str(app),
                    "record",
                    "start",
                    "--profile-id",
                    "retrospective",
                    "--request",
                    "x",
                    "--plan",
                    "override-step",
                    "--from-run",
                    original_id,
                ]
            )
            retro_id = out.getvalue().strip()
        retro_run = next(run for run in list_runs(app) if run.invocation_id == retro_id)
        self.assertEqual(list(retro_run.plan), ["override-step"])

    def test_from_run_with_unknown_id_fails_clearly(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(
                main(
                    [
                        "-C",
                        str(app),
                        "record",
                        "start",
                        "--profile-id",
                        "retrospective",
                        "--request",
                        "x",
                        "--from-run",
                        "deadbeef",
                    ]
                ),
                1,
            )
            self.assertIn("no start record", err.getvalue())

    def test_retrospective_requires_from_run(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(
                main(
                    [
                        "-C",
                        str(app),
                        "record",
                        "start",
                        "--profile-id",
                        "retrospective",
                        "--request",
                        "retro without source",
                    ]
                ),
                1,
            )
            self.assertIn("require --from-run", err.getvalue())

    def test_from_run_with_no_step_history_fails(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(
                main(
                    [
                        "-C",
                        str(app),
                        "record",
                        "start",
                        "--profile-id",
                        "generic-agent",
                        "--request",
                        "no-step source",
                    ]
                ),
                0,
            )
            source_id = out.getvalue().strip()
        with patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(
                main(["-C", str(app), "record", "complete", "--id", source_id, "--outcome", "failed"]),
                0,
            )
        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(
                main(
                    [
                        "-C",
                        str(app),
                        "record",
                        "start",
                        "--profile-id",
                        "retrospective",
                        "--request",
                        "retro",
                        "--from-run",
                        source_id,
                    ]
                ),
                1,
            )
            self.assertIn("no recorded steps", err.getvalue())
