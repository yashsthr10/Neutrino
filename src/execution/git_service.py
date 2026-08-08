"""Git operations for Tool Engine git.* tools (subprocess git, no GitPython)."""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class GitOpResult:
    success: bool
    data: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GitService:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def diff(self, *, staged: bool = False, path: str | None = None) -> GitOpResult:
        args = ["git", "diff", "--staged"] if staged else ["git", "diff"]
        if path:
            args.extend(["--", path])
        code, out, err = self._run(args)
        if code != 0:
            return GitOpResult(success=False, data={}, error=err or out or "git diff failed")
        return GitOpResult(
            success=True,
            data={"staged": staged, "path": path, "diff": out},
        )

    def commit(self, *, message: str = "") -> GitOpResult:
        msg = message.strip() or "neutrino: apply changes"
        # Stage modified/untracked under repo (respects .gitignore)
        add_code, _, add_err = self._run(["git", "add", "-A"])
        if add_code != 0:
            return GitOpResult(success=False, data={}, error=add_err or "git add failed")
        status_code, status_out, _ = self._run(["git", "status", "--porcelain"])
        if status_code != 0:
            return GitOpResult(success=False, data={}, error="git status failed")
        if not status_out.strip():
            return GitOpResult(
                success=False,
                data={"committed": False},
                error="nothing to commit",
            )
        code, out, err = self._run(["git", "commit", "-m", msg])
        if code != 0:
            return GitOpResult(success=False, data={}, error=err or out or "git commit failed")
        sha_code, sha, _ = self._run(["git", "rev-parse", "HEAD"])
        return GitOpResult(
            success=True,
            data={
                "committed": True,
                "message": msg,
                "sha": sha.strip() if sha_code == 0 else None,
                "output": out,
            },
        )

    def undo(self) -> GitOpResult:
        """Undo the last commit if it has not been pushed (soft reset + restore)."""
        code, log, err = self._run(["git", "log", "-1", "--pretty=%s"])
        if code != 0:
            return GitOpResult(success=False, data={}, error=err or "no commits")
        subject = log.strip()
        # Prefer soft undo of neutrino commits; still allow general soft reset of HEAD~1
        # when working tree is clean enough — use `git reset --soft HEAD~1` then
        # `git restore --staged --worktree .` is destructive. Safer: `git reset --mixed HEAD~1`.
        code, out, err = self._run(["git", "reset", "--mixed", "HEAD~1"])
        if code != 0:
            return GitOpResult(success=False, data={}, error=err or out or "git reset failed")
        return GitOpResult(
            success=True,
            data={"undone_subject": subject, "output": out},
        )

    def _run(self, args: list[str]) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                args,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return 1, "", str(exc)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
