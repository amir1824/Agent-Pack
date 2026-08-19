from __future__ import annotations

import unittest
from pathlib import Path

from agent_pack.errors import PackError
from agent_pack.git import tag_ref, validate_ref, validate_source


class ValidateSourceTest(unittest.TestCase):
    def test_rejects_option_lookalike(self) -> None:
        # git would parse these as options, not as a repository.
        for bad in ("--upload-pack=touch /tmp/pwned", "-c", "--config=x"):
            with self.subTest(bad=bad), self.assertRaises(PackError) as ctx:
                validate_source(bad)
            self.assertIn("must not start with", str(ctx.exception))

    def test_rejects_shell_transport(self) -> None:
        for bad in ("ext::sh -c id", "ext::whoami"):
            with self.subTest(bad=bad), self.assertRaises(PackError) as ctx:
                validate_source(bad)
            self.assertIn("unsupported transport", str(ctx.exception))

    def test_rejects_credentials_in_url(self) -> None:
        for bad in (
            "https://ghp_secret@github.com/org/repo.git",
            "https://user:pass@github.com/org/repo.git",
            "http://token@example.com/repo.git",
        ):
            with self.subTest(bad=bad), self.assertRaises(PackError) as ctx:
                validate_source(bad)
            self.assertIn("credential", str(ctx.exception))

    def test_accepts_ssh_and_plain_https(self) -> None:
        for good in (
            "git@github.com:org/repo.git",
            "ssh://git@github.com/org/repo.git",
            "https://github.com/org/repo.git",
            "git://example.com/repo.git",
            "file:///srv/packs/repo.git",
        ):
            with self.subTest(good=good):
                self.assertEqual(validate_source(good), good)

    def test_accepts_local_path(self) -> None:
        self.assertEqual(validate_source("/srv/packs/repo"), "/srv/packs/repo")
        self.assertEqual(validate_source("../sibling-pack"), "../sibling-pack")

    def test_rejects_empty(self) -> None:
        with self.assertRaises(PackError):
            validate_source("   ")


class ValidateRefTest(unittest.TestCase):
    def test_rejects_bad_refs(self) -> None:
        for bad in ("--force", "-v", "a..b", "v1^", "v1~2", "v1:v2", "", "  ", "refs.lock"):
            with self.subTest(bad=bad), self.assertRaises(PackError):
                validate_ref(bad)

    def test_accepts_normal_tags(self) -> None:
        for good in ("v1.0.0", "release/2026-08", "v2.0.0-rc1"):
            with self.subTest(good=good):
                self.assertEqual(validate_ref(good), good)

    def test_tag_ref_is_fully_qualified(self) -> None:
        self.assertEqual(tag_ref("v1.0.0"), "refs/tags/v1.0.0")


class SafeDestTest(unittest.TestCase):
    def test_rejects_escape(self) -> None:
        from agent_pack.pack import safe_dest

        root = Path("/tmp/app-root")
        with self.assertRaises(PackError):
            safe_dest(root, "../outside/evil.md")
        self.assertEqual(safe_dest(root, ".agents/skills/x/SKILL.md"), root / ".agents/skills/x/SKILL.md")


if __name__ == "__main__":
    unittest.main()
