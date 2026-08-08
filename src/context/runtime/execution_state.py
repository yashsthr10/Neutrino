"""ExecutionState — code changes, tool results, iteration status owned by Executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ExecutionState:
    code_changes: tuple[dict, ...] = ()
    tool_results: tuple[dict, ...] = ()
    iteration_count: int = 0
    status: Literal["INIT", "RUNNING", "DONE", "FAIL"] = "INIT"
