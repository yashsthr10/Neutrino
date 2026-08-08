"""Execution — file apply, shell, and git ops for the coding agent."""

from __future__ import annotations

from src.execution.git_service import GitOpResult, GitService
from src.execution.models import ApplyFailure, ApplyResult, FileChange, ShellResult
from src.execution.service import ExecutionPort, ExecutionService, build_execution_service

__all__ = [
    "ApplyFailure",
    "ApplyResult",
    "ExecutionPort",
    "ExecutionService",
    "FileChange",
    "GitOpResult",
    "GitService",
    "ShellResult",
    "build_execution_service",
]
