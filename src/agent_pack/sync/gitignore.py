from __future__ import annotations

from pathlib import Path

GITIGNORE_RULE = ".agents/log/"


def ensure_gitignore(app_root: Path, rule: str = GITIGNORE_RULE) -> None:
    path = app_root / ".gitignore"
    if not path.exists():
        path.write_text(rule + "\n", encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    existing = {line.strip() for line in text.splitlines()}
    if rule in existing or rule.rstrip("/") in existing:
        return
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + rule + "\n", encoding="utf-8")

