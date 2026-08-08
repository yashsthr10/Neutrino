"""Thin lint/test command runners for Tool Engine verification.* tools."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Protocol, runtime_checkable

from src.execution.shell import run_shell
from src.verification.models import RunnerResult


@runtime_checkable
class VerificationPort(Protocol):
    def run_tests(self, *, target: str | None = None) -> RunnerResult: ...

    def run_lint(self, *, paths: list[str] | None = None) -> RunnerResult: ...


class VerificationService:
    def __init__(
        self,
        repo_root: Path,
        *,
        test_command: str = "pytest",
        lint_command: str = "ruff check",
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.test_command = test_command
        self.lint_command = lint_command

    def run_tests(self, *, target: str | None = None) -> RunnerResult:
        cmd = self.test_command
        if target:
            cmd = f"{cmd} {shlex.quote(target)}"
        return self._run(cmd, kind="tests")

    def run_lint(self, *, paths: list[str] | None = None) -> RunnerResult:
        cmd = self.lint_command
        if paths:
            quoted = " ".join(shlex.quote(p) for p in paths)
            cmd = f"{cmd} {quoted}"
        return self._run(cmd, kind="lint")

    def _run(self, command: str, *, kind: str) -> RunnerResult:
        # Verification runners are explicitly invoked tools — treat as approved.
        result = run_shell(command, cwd=self.repo_root, approved=True, timeout_s=300.0)
        return RunnerResult(
            success=result.success,
            kind=kind,
            command=result.command,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            truncated=result.truncated,
            error=None if result.success else (result.stderr or f"exit {result.exit_code}"),
        )


def build_verification_service(
    repo_root: Path | str,
    *,
    test_command: str = "pytest",
    lint_command: str = "ruff check",
) -> VerificationService:
    return VerificationService(
        Path(repo_root),
        test_command=test_command,
        lint_command=lint_command,
    )
