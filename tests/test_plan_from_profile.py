from __future__ import annotations

import io
from unittest.mock import patch

from agent_pack.cli import main
from agent_pack.log import list_runs
from agent_pack.pack import init_pack
from tests.test_cli import PackRepoTest, _commit_all, _git


def _write_profile(pack, profile_id: str, plan=None) -> None:
    lines = [
        f"profile-id: {profile_id}",
        f"name: {profile_id.title()}",
        "description: test profile.",
    ]
    if plan is not None:
        lines.append("plan:")
        lines.extend(f"  - {step}" for step in plan)
    (pack / "profiles" / f"{profile_id}.agent.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


class ProfilePlanValidationTest(PackRepoTest):
    def test_valid_plan_passes(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        for step in ("product", "designer", "qa"):
            _write_profile(pack, step)
        _write_profile(pack, "generic-agent", ["product", "designer", "qa"])
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(pack), "validate"]), 0)
            self.assertIn("ok", out.getvalue())

    def test_plan_step_not_matching_a_profile_id_is_rejected(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        _write_profile(pack, "generic-agent", ["product", "nonexistent-role"])
        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(main(["-C", str(pack), "validate"]), 1)
            self.assertIn("'nonexistent-role' does not match any profile-id", err.getvalue())

    def test_duplicate_plan_entries_rejected(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        _write_profile(pack, "generic-agent", ["product", "product"])
        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(main(["-C", str(pack), "validate"]), 1)
            self.assertIn("plan entries must be unique", err.getvalue())

    def test_empty_plan_list_rejected(self) -> None:
        pack = self.root / "fresh"
        init_pack(pack, "fresh")
        (pack / "profiles" / "generic-agent.agent.yaml").write_text(
            "profile-id: generic-agent\nname: Generic\ndescription: d.\nplan: []\n", encoding="utf-8"
        )
        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(main(["-C", str(pack), "validate"]), 1)
            self.assertIn("plan must be a non-empty list", err.getvalue())


class ProfilePlanDefaultTest(PackRepoTest):
    def _bound_app(self, plan):
        pack = self._pack_repo()
        for step in plan or ():
            _write_profile(pack, step)
        _write_profile(pack, "generic-agent", plan)
        _commit_all(pack, "feat: give generic-agent a plan")
        _git(pack, "tag", "-f", "v1.0.0")
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        return app

    def test_record_start_uses_profile_plan_when_no_flag(self) -> None:
        app = self._bound_app(["product", "designer", "qa"])
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(
                main(
                    ["-C", str(app), "record", "start", "--profile-id", "generic-agent", "--request", "x"]
                ),
                0,
            )
            invocation_id = out.getvalue().strip()
        run = list_runs(app)[0]
        self.assertEqual(list(run.plan), ["product", "designer", "qa"])

    def test_explicit_flag_overrides_profile_plan(self) -> None:
        app = self._bound_app(["product", "designer", "qa"])
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
                        "solo-step",
                    ]
                ),
                0,
            )
        run = list_runs(app)[0]
        self.assertEqual(list(run.plan), ["solo-step"])

    def test_profile_with_no_plan_yields_empty_plan(self) -> None:
        app = self._bound_app(None)
        with patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(
                main(
                    ["-C", str(app), "record", "start", "--profile-id", "generic-agent", "--request", "x"]
                ),
                0,
            )
        run = list_runs(app)[0]
        self.assertEqual(run.plan, ())

    def test_corrupt_profile_yaml_fails_record_start(self) -> None:
        app = self._bound_app(["product"])
        profile = app / ".agents" / "profiles" / "generic-agent.agent.yaml"
        profile.write_text("profile-id: [broken\n", encoding="utf-8")
        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(
                main(
                    ["-C", str(app), "record", "start", "--profile-id", "generic-agent", "--request", "x"]
                ),
                1,
            )
            self.assertIn("cannot read profile plan", err.getvalue())
