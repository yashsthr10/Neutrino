"""Blame / co-change ranking signals."""

from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path


class GitHistory:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path.resolve()

    def co_changed_files(self, target: str, *, limit: int = 20) -> list[tuple[str, float]]:
        """
        Files historically committed together with `target`.
        Returns (path, score) sorted descending.
        """
        try:
            # commits touching target
            log = subprocess.run(
                ["git", "log", "--pretty=format:%H", "--", target],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        commits = [c for c in log.stdout.splitlines() if c.strip()][:50]
        if not commits:
            return []
        counts: Counter[str] = Counter()
        for commit in commits:
            try:
                show = subprocess.run(
                    ["git", "show", "--name-only", "--pretty=format:", commit],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            for path in show.stdout.splitlines():
                path = path.strip().replace("\\", "/")
                if not path or path == target:
                    continue
                counts[path] += 1
        if not counts:
            return []
        max_c = max(counts.values())
        ranked = [(p, counts[p] / max_c) for p in counts]
        ranked.sort(key=lambda t: (-t[1], t[0]))
        return ranked[:limit]

    def is_git_repo(self) -> bool:
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            return proc.returncode == 0 and proc.stdout.strip() == "true"
        except (OSError, subprocess.TimeoutExpired):
            return False
