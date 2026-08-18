from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_pack.cli import main
from agent_pack.source import init_pack
from agent_pack.validate import validate_pack


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_git(repo: Path) -> None:
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "pack@test")
    _git(repo, "config", "user.name", "Pack Test")


def _commit_all(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)


class PackRepoTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self._old_cache = os.environ.get("AGENT_PACK_CACHE")
        os.environ["AGENT_PACK_CACHE"] = str(self.cache)

    def tearDown(self) -> None:
        if self._old_cache is None:
            os.environ.pop("AGENT_PACK_CACHE", None)
        else:
            os.environ["AGENT_PACK_CACHE"] = self._old_cache
        self._tmp.cleanup()

    def _pack_repo(self) -> Path:
        pack = self.root / "pack-src"
        pack.mkdir()
        init_pack(pack, "team-pack")
        _init_git(pack)
        _commit_all(pack, "feat: initial pack")
        _git(pack, "tag", "v1.0.0")
        return pack

    def _app_repo(self) -> Path:
        app = self.root / "app"
        app.mkdir()
        _init_git(app)
        (app / "README.md").write_text("app\n", encoding="utf-8")
        (app / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        _commit_all(app, "chore: app root")
        return app


class PackCliTest(PackRepoTest):

    def test_validate_init_layout(self) -> None:
        pack = self.root / "fresh"
        self.assertEqual(main(["-C", str(pack), "init", "--name", "fresh"]), 0)
        self.assertEqual(validate_pack(pack), [])

    def test_validate_rejects_symlink(self) -> None:
        pack = self.root / "linked"
        init_pack(pack, "linked")
        target = pack / "skills" / "example" / "SKILL.md"
        (pack / "skills" / "example" / "alias.md").symlink_to(target)
        self.assertIn("symlink not allowed: skills/example/alias.md", validate_pack(pack))

    def test_bind_sync_status_and_gitignore(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(
            main(["-C", str(app), "bind", str(pack), "--name", "team", "--tag", "v1.0.0"]),
            0,
        )
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "status"]), 0)
            self.assertIn("state: not synced", out.getvalue())
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        skill = app / ".agents" / "skills" / "example" / "SKILL.md"
        self.assertTrue(skill.is_file())
        self.assertFalse(skill.is_symlink())
        lock_data = json.loads((app / "agent-pack.lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock_data["tag"], "v1.0.0")
        self.assertIn(".agents/skills/example/SKILL.md", lock_data["files"])
        self.assertTrue((app / ".cursor" / "skills" / "example" / "SKILL.md").is_file())
        gitignore = (app / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("node_modules/", gitignore)
        self.assertIn(".agents/log/", gitignore)
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["status", "-C", str(app)]), 0)
            self.assertIn("state: clean", out.getvalue())
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "check"]), 0)
            self.assertIn("state: clean", out.getvalue())
        self.assertTrue((app / ".agents" / "constitution.md").is_file())

    def test_status_dirty_and_diff(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        skill = app / ".agents" / "skills" / "example" / "SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "status"]), 0)
            self.assertIn("modified: .agents/skills/example/SKILL.md", out.getvalue())
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "check"]), 1)
            self.assertIn("state: dirty", out.getvalue())
            self.assertIn("modified: .agents/skills/example/SKILL.md", out.getvalue())
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "diff"]), 0)
            self.assertIn("local edit", out.getvalue())

    def test_upgrade_adds_and_sync_removes_stale(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "sync"]), 0)
        shipped = pack / "skills" / "shipped"
        shipped.mkdir()
        (shipped / "SKILL.md").write_text(
            "---\nname: shipped\ndescription: Added in v1.0.1\n---\n\n# Shipped\n",
            encoding="utf-8",
        )
        example = pack / "skills" / "example" / "SKILL.md"
        example.unlink()
        example.parent.rmdir()
        _commit_all(pack, "feat: replace example with shipped")
        _git(pack, "tag", "v1.0.1")
        self.assertEqual(main(["-C", str(app), "upgrade", "--tag", "v1.0.1"]), 0)
        self.assertTrue((app / ".agents" / "skills" / "shipped" / "SKILL.md").is_file())
        self.assertTrue((app / ".cursor" / "skills" / "shipped" / "SKILL.md").is_file())
        self.assertFalse((app / ".agents" / "skills" / "example" / "SKILL.md").exists())
        self.assertFalse((app / ".cursor" / "skills" / "example" / "SKILL.md").exists())
        self.assertFalse((app / ".claude" / "skills" / "example" / "SKILL.md").exists())

    def test_check_not_synced(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "check"]), 1)
            self.assertIn("state: not synced", out.getvalue())

    def test_validate_requires_constitution(self) -> None:
        pack = self.root / "no-const"
        init_pack(pack, "no-const")
        (pack / "constitution.md").write_text(" \n", encoding="utf-8")
        self.assertIn("constitution.md: must not be empty", validate_pack(pack))
        (pack / "constitution.md").unlink()
        self.assertIn("missing constitution.md", validate_pack(pack))

    def test_record_start_complete_and_log(self) -> None:
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
                        "verifier",
                        "--request",
                        "review the diff",
                    ]
                ),
                0,
            )
            invocation_id = out.getvalue().strip()
        self.assertTrue((app / ".agents" / "log" / f"{invocation_id}.jsonl").is_file())
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(
                main(["-C", str(app), "record", "complete", "--id", invocation_id, "--outcome", "done"]),
                0,
            )
            self.assertIn("done", out.getvalue())
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "log"]), 0)
            self.assertIn("verifier", out.getvalue())
            self.assertIn("done", out.getvalue())
            self.assertIn("review the diff", out.getvalue())

    def test_bind_twice_fails(self) -> None:
        pack = self._pack_repo()
        app = self._app_repo()
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 0)
        self.assertEqual(main(["-C", str(app), "bind", str(pack), "--tag", "v1.0.0"]), 1)

    def test_log_table(self) -> None:
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
        with patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(main(["-C", str(app), "log"]), 0)
            self.assertIn("generic-agent", out.getvalue())
            self.assertIn("done", out.getvalue())

    def test_this_repo_is_a_valid_pack(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        self.assertEqual(validate_pack(repo), [])


if __name__ == "__main__":
    unittest.main()
