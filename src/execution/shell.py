"""Shell command runners for executor.run and terminal.run."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from src.config.constants import SHELL_MAX_OUTPUT_CHARS
from src.execution.models import ShellResult
from src.execution.paths import PathSecurityError, resolve_repo_path


def run_shell(
    command: str,
    *,
    cwd: Path,
    timeout_s: float = 120.0,
    approved: bool = False,
) -> ShellResult:
    """Run a shell command in the repo root (executor.run)."""
    return run_terminal(
        command,
        repo_root=cwd,
        cwd=None,
        timeout_s=timeout_s,
        approved=approved,
    )


def run_terminal(
    command: str,
    *,
    repo_root: Path,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
    timeout_s: float = 600.0,
    approved: bool = False,
) -> ShellResult:
    """Run a shell command with optional cwd, env, and stdin (terminal.run)."""
    if not approved:
        return ShellResult(
            success=False,
            command=command,
            exit_code=-1,
            stdout="",
            stderr="Shell execution requires approved=true (host/TUI must confirm).",
            needs_approval=True,
            cwd=cwd,
        )
    if not command.strip():
        return ShellResult(
            success=False,
            command=command,
            exit_code=-1,
            stdout="",
            stderr="Empty command",
            cwd=cwd,
        )

    work_dir = repo_root.resolve()
    if cwd is not None and cwd.strip():
        try:
            work_dir = resolve_repo_path(repo_root, cwd.strip())
        except PathSecurityError as exc:
            return ShellResult(
                success=False,
                command=command,
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                cwd=cwd,
            )

    run_env = os.environ.copy()
    if env:
        for key, value in env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                return ShellResult(
                    success=False,
                    command=command,
                    exit_code=-1,
                    stdout="",
                    stderr="env keys and values must be strings",
                    cwd=cwd,
                )
            run_env[key] = value

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env=run_env,
            input=stdin,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        err = (exc.stderr or "") if isinstance(exc.stderr, str) else "timeout"
        return ShellResult(
            success=False,
            command=command,
            exit_code=-1,
            stdout=_truncate(out),
            stderr=_truncate(err or f"Command timed out after {timeout_s}s"),
            truncated=len(out) > SHELL_MAX_OUTPUT_CHARS or len(err) > SHELL_MAX_OUTPUT_CHARS,
            cwd=cwd,
        )
    except OSError as exc:
        return ShellResult(
            success=False,
            command=command,
            exit_code=-1,
            stdout="",
            stderr=str(exc),
            cwd=cwd,
        )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    truncated = len(stdout) > SHELL_MAX_OUTPUT_CHARS or len(stderr) > SHELL_MAX_OUTPUT_CHARS
    return ShellResult(
        success=proc.returncode == 0,
        command=command,
        exit_code=proc.returncode,
        stdout=_truncate(stdout),
        stderr=_truncate(stderr),
        truncated=truncated,
        cwd=cwd,
    )


def _truncate(text: str) -> str:
    if len(text) <= SHELL_MAX_OUTPUT_CHARS:
        return text
    return text[:SHELL_MAX_OUTPUT_CHARS] + "\n...[truncated]...\n"
