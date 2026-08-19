from __future__ import annotations

import io
from unittest.mock import patch

from agent_pack.cli import main
from tests.test_cli import PackRepoTest


class PlanEnforcementTest(PackRepoTest):
    def _started_run(self, app, plan="product,designer,qa") -> str:
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
                        "x",
                        "--plan",
                        plan,
                    ]
                ),
                0,
            )
            return out.getvalue().strip()

    def _finish_step(self, app, invocation_id: str, name: str) -> None:
        with patch("sys.stdout", new=io.StringIO()):
            for status in ("started", "done"):
                self.assertEqual(
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
                            status,
                        ]
                    ),
                    0,
                )

    def test_step_outside_plan_is_rejected(self) -> None:
        _pack, app = self._bound_app()
        invocation_id = self._started_run(app)

        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(
                main(
                    [
                        "-C",
                        str(app),
                        "record",
                        "step",
                        "--id",
                        invocation_id,
                        "--name",
                        "unplanned",
                        "--status",
                        "done",
                    ]
                ),
                1,
            )
            self.assertIn("not in the plan", err.getvalue())

    def test_force_allows_a_step_outside_plan(self) -> None:
        _pack, app = self._bound_app()
        invocation_id = self._started_run(app)

        with patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(
                main(
                    [
                        "-C",
                        str(app),
                        "record",
                        "step",
                        "--id",
                        invocation_id,
                        "--name",
                        "unplanned",
                        "--status",
                        "done",
                        "--force",
                    ]
                ),
                0,
            )

    def test_complete_done_blocked_until_every_planned_step_is_done(self) -> None:
        _pack, app = self._bound_app()
        invocation_id = self._started_run(app)

        for name in ("product", "designer"):
            self._finish_step(app, invocation_id, name)

        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(
                main(["-C", str(app), "record", "complete", "--id", invocation_id, "--outcome", "done"]),
                1,
            )
            self.assertIn("qa", err.getvalue())

        self._finish_step(app, invocation_id, "qa")
        with patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(
                main(["-C", str(app), "record", "complete", "--id", invocation_id, "--outcome", "done"]),
                0,
            )

    def test_complete_done_rejects_step_done_without_started(self) -> None:
        _pack, app = self._bound_app()
        invocation_id = self._started_run(app)

        with patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(
                main(
                    [
                        "-C",
                        str(app),
                        "record",
                        "step",
                        "--id",
                        invocation_id,
                        "--name",
                        "product",
                        "--status",
                        "done",
                    ]
                ),
                0,
            )

        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(
                main(["-C", str(app), "record", "complete", "--id", invocation_id, "--outcome", "done"]),
                1,
            )
            self.assertIn("product", err.getvalue())

    def test_force_completes_done_despite_unfinished_steps(self) -> None:
        _pack, app = self._bound_app()
        invocation_id = self._started_run(app)

        with patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(
                main(
                    [
                        "-C",
                        str(app),
                        "record",
                        "complete",
                        "--id",
                        invocation_id,
                        "--outcome",
                        "done",
                        "--force",
                    ]
                ),
                0,
            )

    def test_failed_and_abandoned_are_never_blocked_by_the_plan(self) -> None:
        _pack, app = self._bound_app()

        for outcome in ("failed", "abandoned"):
            invocation_id = self._started_run(app)
            with patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(
                    main(
                        ["-C", str(app), "record", "complete", "--id", invocation_id, "--outcome", outcome]
                    ),
                    0,
                )

    def test_run_with_no_plan_is_never_blocked(self) -> None:
        _pack, app = self._bound_app()
        invocation_id = self._started_run(app, plan="")

        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(
                main(
                    [
                        "-C",
                        str(app),
                        "record",
                        "step",
                        "--id",
                        invocation_id,
                        "--name",
                        "anything",
                        "--status",
                        "done",
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(["-C", str(app), "record", "complete", "--id", invocation_id, "--outcome", "done"]),
                0,
            )
