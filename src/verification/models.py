"""Verification runner result shapes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RunnerResult:
    success: bool
    kind: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
