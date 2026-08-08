"""Path resolution and safety for execution under a repo root."""

from __future__ import annotations

from pathlib import Path


class PathSecurityError(ValueError):
    """Raised when a path escapes the repository root."""


def resolve_repo_path(repo_root: Path, rel_path: str) -> Path:
    root = repo_root.resolve()
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PathSecurityError(f"Path escapes repository root: {rel_path}") from exc
    return candidate


def to_rel_path(repo_root: Path, abs_path: Path) -> str:
    return abs_path.resolve().relative_to(repo_root.resolve()).as_posix()
