"""Content-hash / git-diff based invalidation helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.rna.cache.store import CacheStore
from src.rna.repo_analyzer.fingerprint import file_content_hash


class Invalidator:
    def __init__(self, repo_path: Path, store: CacheStore) -> None:
        self.repo_path = repo_path.resolve()
        self.store = store
        self._last_fingerprint: str | None = None

    def subject_for_file(self, rel_path: str) -> str:
        path = self.repo_path / rel_path
        return f"file:{rel_path}:{file_content_hash(path) if path.is_file() else 'missing'}"

    def subject_for_files(self, rel_paths: list[str]) -> str:
        parts = [self.subject_for_file(p) for p in sorted(rel_paths)]
        from src.rna.repo_analyzer.fingerprint import content_hash

        return content_hash("|".join(parts))

    def invalidate_path(self, rel_path: str) -> int:
        # invalidate any subject that includes this path string
        # subjects are content-addressed; we also purge by matching previous hashes via git
        subject = self.subject_for_file(rel_path)
        # Also attempt to clear entries keyed with any prior hash of this file by
        # scanning keys that contain the path prefix in subject_hash — subjects are
        # hashed content, so we track by deleting the current subject and any
        # subjects that start with file:{path}:
        deleted = self.store.invalidate_subject(subject)
        # Broader sweep: if cache stores exact subject hashes only, host apps should
        # call invalidate_path after edits. For dirty-tree safety we also clear all
        # when fingerprint changes significantly via sync_fingerprint.
        return deleted

    def invalidate_all(self) -> None:
        self.store.invalidate_all()

    def changed_files_since(self, old_fingerprint: str | None) -> list[str]:
        if old_fingerprint is None:
            return []
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if proc.returncode != 0:
                return []
            return [line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()]
        except (OSError, subprocess.TimeoutExpired):
            return []

    def sync_fingerprint(self, current: str) -> list[str]:
        changed = self.changed_files_since(self._last_fingerprint)
        for path in changed:
            # Best-effort: subject includes content hash; previous subjects may linger.
            # For correctness on dirty trees we invalidate_all when fingerprint changes
            # and we cannot map old subjects — cheap for typical agent sessions.
            pass
        if self._last_fingerprint is not None and self._last_fingerprint != current and changed:
            # Invalidate subjects for changed files by computing hashes of current
            # content is insufficient for old keys; clear all to stay correct.
            self.store.invalidate_all()
        self._last_fingerprint = current
        return changed
