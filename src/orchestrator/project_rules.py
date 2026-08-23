"""Load project rules files (NEUTRINO.md / .neutrino/rules)."""

from __future__ import annotations

from pathlib import Path

from src.config.constants import PROJECT_RULES_MAX_CHARS

_CANDIDATES = (
    "NEUTRINO.md",
    ".neutrino/rules.md",
    ".neutrino/NEUTRINO.md",
    ".neutrino/rules",
)


def load_project_rules(repo_path: Path) -> str | None:
    root = repo_path.resolve()
    for name in _CANDIDATES:
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not text:
            continue
        if len(text) > PROJECT_RULES_MAX_CHARS:
            text = text[: PROJECT_RULES_MAX_CHARS - 40] + "\n\n...(project rules truncated)"
        return text
    return None
