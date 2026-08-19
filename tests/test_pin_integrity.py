from __future__ import annotations

import io
import json
from unittest.mock import patch

from agent_pack.cli import main
from tests.test_cli import PackRepoTest, _commit_all, _git


class PinIntegrityTest(PackRepoTest):
    def _move_tag(self, pack) -> None:
        (pack / "skills" / "example" / "SKILL.md").write_text(
            "---\nname: example\ndescription: swapped instructions.\n---\n\n# Owned\n",
            encoding="utf-8",
        )
        _commit_all(pack, "feat: swap the skill")
        _git(pack, "tag", "-f", "v1.0.0")

    def test_sync_refuses_a_moved_tag(self) -> None:
        pack, app = self._bound_app()
        before = (app / ".agents" / "skills" / "example" / "SKILL.md").read_text(encoding="utf-8")
        pinned = json.loads((app / "agent-pack.lock.json").read_text(encoding="utf-8"))["commit"]
        self._move_tag(pack)

        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(main(["-C", str(app), "sync"]), 1)
            message = err.getvalue()
        self.assertIn("pinned tag v1.0.0 moved", message)

        # nothing was copied and the pin did not drift
        after = (app / ".agents" / "skills" / "example" / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(before, after)
        self.assertNotIn("Owned", after)
        self.assertEqual(json.loads((app / "agent-pack.lock.json").read_text(encoding="utf-8"))["commit"], pinned)

    def test_allow_tag_move_opts_in(self) -> None:
        pack, app = self._bound_app()
        self._move_tag(pack)
        with patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(main(["-C", str(app), "sync", "--allow-tag-move"]), 0)
        self.assertIn("Owned", (app / ".agents" / "skills" / "example" / "SKILL.md").read_text(encoding="utf-8"))

    def test_upgrade_accepts_a_moved_tag(self) -> None:
        pack, app = self._bound_app()
        self._move_tag(pack)
        with patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(main(["-C", str(app), "upgrade", "--tag", "v1.0.0"]), 0)
        self.assertIn("Owned", (app / ".agents" / "skills" / "example" / "SKILL.md").read_text(encoding="utf-8"))

    def test_diff_warns_about_a_moved_tag(self) -> None:
        pack, app = self._bound_app()
        self._move_tag(pack)
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "diff"]), 0)
            report = out.getvalue()
        self.assertIn("warning: tag v1.0.0 moved", report)

    def test_sync_is_clean_when_the_tag_stays_put(self) -> None:
        _pack, app = self._bound_app()
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "sync"]), 0)
            self.assertIn("synced", out.getvalue())


class SourceGuardTest(PackRepoTest):
    def test_bind_refuses_a_token_url(self) -> None:
        app = self._app_repo()
        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(main(["-C", str(app), "bind", "https://ghp_secret@github.com/o/r.git"]), 1)
            self.assertIn("credential", err.getvalue())
        self.assertFalse((app / "agent-pack.lock.json").exists())

    def test_bind_refuses_a_shell_transport(self) -> None:
        app = self._app_repo()
        with patch("sys.stderr", new=io.StringIO()) as err:
            self.assertEqual(main(["-C", str(app), "bind", "ext::sh -c id"]), 1)
            self.assertIn("unsupported transport", err.getvalue())
        self.assertFalse((app / "agent-pack.lock.json").exists())


class LocalAdditionsTest(PinIntegrityTest):
    def test_extra_files_pass_check_but_are_still_reported(self) -> None:
        _pack, app = self._bound_app()

        own = app / ".agents" / "skills" / "my-own"
        own.mkdir(parents=True)
        (own / "SKILL.md").write_text(
            "---\nname: my-own\ndescription: mine.\n---\n\n# Mine\n", encoding="utf-8"
        )

        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "status"]), 0)
            report = out.getvalue()
        self.assertIn("state: clean", report)
        self.assertIn("extra: .agents/skills/my-own/SKILL.md", report)

        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "check"]), 0)
            report = out.getvalue()
        self.assertIn("extra: .agents/skills/my-own/SKILL.md", report)

    def test_extra_does_not_mask_real_drift(self) -> None:
        _pack, app = self._bound_app()

        own = app / ".agents" / "skills" / "my-own"
        own.mkdir(parents=True)
        (own / "SKILL.md").write_text("mine\n", encoding="utf-8")
        skill = app / ".agents" / "skills" / "example" / "SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")

        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "check"]), 1)
            report = out.getvalue()
        self.assertIn("state: dirty", report)
        self.assertIn("modified: .agents/skills/example/SKILL.md", report)
        self.assertIn("extra: .agents/skills/my-own/SKILL.md", report)
