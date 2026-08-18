from __future__ import annotations

import io
import json
from unittest.mock import patch

from agent_pack.cli import main
from tests.test_cli import PackRepoTest


class HostAdapterTest(PackRepoTest):
    def test_sync_host_adapters(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        (app / "AGENTS.md").write_text("# App agents\nkeep me\n", encoding="utf-8")
        local = app / ".cursor" / "skills" / "local-only"
        local.mkdir(parents=True)
        (local / "SKILL.md").write_text("# local\n", encoding="utf-8")
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--name", "team", "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        canonical = (app / ".agents" / "skills" / "example" / "SKILL.md").read_text(encoding="utf-8")
        cursor = app / ".cursor" / "skills" / "example" / "SKILL.md"
        claude = app / ".claude" / "skills" / "example" / "SKILL.md"
        self.assertEqual(cursor.read_text(encoding="utf-8"), canonical)
        self.assertFalse(cursor.is_symlink())
        self.assertFalse(claude.is_symlink())
        lock_data = json.loads((app / "agent-pack.lock.json").read_text(encoding="utf-8"))
        self.assertNotIn("AGENTS.md", lock_data["files"])
        agent = (app / ".claude" / "agents" / "generic-agent.md").read_text(encoding="utf-8")
        self.assertIn("name: generic-agent", agent)
        self.assertEqual(agent.split("---", 2)[-1].strip(), "Default profile when no specialist is assigned.")
        root = (app / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<!-- agent-pack:start -->", root)
        self.assertIn("## Must not", root)
        self.assertIn("keep me", root)
        verifier = (app / ".claude" / "agents" / "verifier.md").read_text(encoding="utf-8")
        self.assertIn("name: verifier", verifier)
        self.assertIn("The valuable output is a block", verifier)
        self.assertTrue((local / "SKILL.md").is_file())

    def test_resync_replaces_symlink_diff_ignores_host(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        local = app / ".cursor" / "skills" / "local-only"
        local.mkdir(parents=True)
        (local / "SKILL.md").write_text("# local\n", encoding="utf-8")
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        cursor = app / ".cursor" / "skills" / "example" / "SKILL.md"
        canonical = (app / ".agents" / "skills" / "example" / "SKILL.md").read_text(encoding="utf-8")
        cursor.unlink()
        cursor.symlink_to(local / "SKILL.md")
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        self.assertFalse(cursor.is_symlink())
        self.assertEqual(cursor.read_text(encoding="utf-8"), canonical)
        self.assertEqual((app / "AGENTS.md").read_text(encoding="utf-8").count("<!-- agent-pack:start -->"), 1)
        cursor.write_text(cursor.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "status"]), 0)
            self.assertIn("modified: .cursor/skills/example/SKILL.md", out.getvalue())
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "diff"]), 0)
            self.assertNotIn(".cursor/", out.getvalue())

    def test_stray_end_marker_does_not_duplicate_block(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        (app / "AGENTS.md").write_text(
            "docs mention <!-- agent-pack:end --> here\nkeep me\n",
            encoding="utf-8",
        )
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        root = (app / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(root.count("<!-- agent-pack:start -->"), 1)
        self.assertIn("keep me", root)
        self.assertIn("docs mention <!-- agent-pack:end --> here", root)
