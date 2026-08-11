"""get_file / get_files_with_name."""

from __future__ import annotations

from pathlib import Path

from src.rna.errors import RnaSecurityError
from src.rna.models import FileSlice
from src.rna.repo_analyzer.tree import RepoTree


class FileService:
    def __init__(self, root: Path, tree: RepoTree, *, max_lines_per_file: int = 200) -> None:
        self.root = root.resolve()
        self.tree = tree
        self.max_lines_per_file = max_lines_per_file

    def resolve_safe(self, path: str) -> Path:
        """Resolve a repo-relative path; raise RnaSecurityError on escape/deny."""
        # reject absolute and traversal early
        candidate = Path(path)
        if candidate.is_absolute():
            raise RnaSecurityError(f"absolute paths are not allowed: {path}")
        # Deny Neutrino agent caches even when the model names them explicitly.
        rel_for_ignore = Path(str(path).replace("\\", "/"))
        if self.tree.is_ignored(rel_for_ignore):
            raise RnaSecurityError(f"path is excluded from RNA access (internal cache): {path}")
        resolved = (self.root / path).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise RnaSecurityError(f"path escapes repo root: {path}") from exc
        # Re-check after resolve (symlink / normalization into a cache dir).
        try:
            rel = resolved.relative_to(self.root)
        except ValueError as exc:
            raise RnaSecurityError(f"path escapes repo root: {path}") from exc
        if self.tree.is_ignored(rel):
            raise RnaSecurityError(f"path is excluded from RNA access (internal cache): {path}")
        # symlink escape: resolved already follows symlinks
        return resolved

    def get_file(
        self,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> tuple[FileSlice | None, str | None, bool]:
        """
        Returns (slice, error, truncated_flag_meta).
        error is 'not_found' or None.
        """
        try:
            resolved = self.resolve_safe(path)
        except RnaSecurityError:
            raise
        if not resolved.is_file():
            return None, "not_found", False
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None, "not_found", False
        lines = text.splitlines(keepends=True)
        total = len(lines)
        truncated = False
        if start_line is None and end_line is None:
            start = 1
            end = total
            if total > self.max_lines_per_file:
                end = self.max_lines_per_file
                truncated = True
        else:
            start = max(1, start_line or 1)
            end = min(total, end_line or total)
            if start > total:
                start = total if total else 1
                end = start
            if end < start:
                end = start
        content = "".join(lines[start - 1 : end]) if total else ""
        rel = str(Path(path)).replace("\\", "/")
        return (
            FileSlice(
                path=rel,
                start_line=start if total else 0,
                end_line=end if total else 0,
                content=content,
                total_lines=total,
                truncated=truncated,
            ),
            None,
            truncated,
        )

    def get_files_with_name(self, pattern: str, *, limit: int = 50) -> list[str]:
        files = self.tree.list_files()
        pattern_l = pattern.lower()
        is_glob = any(ch in pattern for ch in "*?[")
        scored: list[tuple[int, int, str]] = []
        for f in files:
            name = Path(f).name
            name_l = name.lower()
            path_l = f.lower()
            if is_glob:
                import fnmatch

                if not (fnmatch.fnmatch(f, pattern) or fnmatch.fnmatch(name, pattern)):
                    continue
                score = 0
            else:
                if name_l == pattern_l:
                    score = 0
                elif name_l.startswith(pattern_l):
                    score = 1
                elif pattern_l in name_l or pattern_l in path_l:
                    score = 2
                else:
                    # fuzzy: subsequence
                    if not _fuzzy_match(pattern_l, name_l) and not _fuzzy_match(pattern_l, path_l):
                        continue
                    score = 3
            depth = f.count("/")
            scored.append((score, depth, f))
        scored.sort(key=lambda t: (t[0], t[1], t[2]))
        return [f for _, _, f in scored[:limit]]


def _fuzzy_match(needle: str, haystack: str) -> bool:
    if not needle:
        return True
    it = iter(haystack)
    return all(ch in it for ch in needle)
