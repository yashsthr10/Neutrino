"""Directory scan with ignore rules."""

from __future__ import annotations

import fnmatch
from pathlib import Path


DEFAULT_IGNORE_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".rna_cache",
        ".context_cache",
        "dist",
        "build",
        ".next",
        "target",
    }
)

# Always denied for RNA tools (list / read / search) — Neutrino-owned caches.
AGENT_CACHE_DIRS = frozenset({".rna_cache", ".context_cache"})


class RepoTree:
    def __init__(self, root: Path, ignore_patterns: tuple[str, ...] = ()) -> None:
        self.root = root.resolve()
        self.ignore_patterns = ignore_patterns
        self._paths: list[str] | None = None
        self._gitignore_patterns: list[str] = self._load_gitignore()

    def _load_gitignore(self) -> list[str]:
        gi = self.root / ".gitignore"
        if not gi.is_file():
            return []
        patterns: list[str] = []
        try:
            for line in gi.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                patterns.append(line.rstrip("/"))
        except OSError:
            return []
        return patterns

    def is_ignored(self, rel: str | Path) -> bool:
        """Public check used by get_file / search to deny agent-owned caches."""
        path = Path(rel) if not isinstance(rel, Path) else rel
        return self._ignored(path)

    def _ignored(self, rel: Path) -> bool:
        parts = rel.parts
        for part in parts:
            if part in DEFAULT_IGNORE_DIRS or part in AGENT_CACHE_DIRS:
                return True
            # Allow a small set of tooling dirs; ignore other top-level-ish dotdirs.
            if part.startswith(".") and part not in {".", "..", ".github", ".cursor", ".vscode"}:
                return True
        name = rel.name
        for pat in self.ignore_patterns:
            if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(str(rel), pat):
                return True
        for pat in self._gitignore_patterns:
            if pat.startswith("!"):
                continue
            if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(str(rel), pat):
                return True
            if any(fnmatch.fnmatch(p, pat) for p in parts):
                return True
        return False

    def list_files(self, *, refresh: bool = False) -> list[str]:
        if self._paths is not None and not refresh:
            return list(self._paths)
        paths: list[str] = []
        if not self.root.is_dir():
            self._paths = []
            return []
        for p in sorted(self.root.rglob("*")):
            if not p.is_file():
                continue
            try:
                rel = p.relative_to(self.root)
            except ValueError:
                continue
            if self._ignored(rel):
                continue
            paths.append(str(rel).replace("\\", "/"))
        self._paths = paths
        return list(paths)

    def invalidate(self) -> None:
        self._paths = None
