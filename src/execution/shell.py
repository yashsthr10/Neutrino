"""Approved shell command runner for executor.run."""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.config.constants import SHELL_MAX_OUTPUT_CHARS
from src.execution.models import ShellResult


def run_shell(
    command: str,
    *,
    cwd: Path,
    timeout_s: float = 120.0,
    approved: bool = False,
) -> ShellResult:
    if not approved:
        return ShellResult(
            success=False,
            command=command,
            exit_code=-1,
            stdout="",
            stderr="Shell execution requires approved=true (host/TUI must confirm).",
            needs_approval=True,
        )
    if not command.strip():
        return ShellResult(
            success=False,
            command=command,
            exit_code=-1,
            stdout="",
            stderr="Empty command",
        )
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
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
        )
    except OSError as exc:
        return ShellResult(
            success=False,
            command=command,
            exit_code=-1,
            stdout="",
            stderr=str(exc),
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
    )


def _truncate(text: str) -> str:
    if len(text) <= SHELL_MAX_OUTPUT_CHARS:
        return text
    return text[:SHELL_MAX_OUTPUT_CHARS] + "\n...[truncated]...\n"
