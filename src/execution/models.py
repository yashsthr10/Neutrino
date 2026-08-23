"""Execution service wire models — apply results and change tracking."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EditFormat = Literal["patch", "search_replace", "udiff", "auto"]


@dataclass(frozen=True, slots=True)
class ApplyFailure:
    path: str
    reason: str
    search: str | None = None
    similar: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FileChange:
    path: str
    action: Literal["add", "update", "delete"]
    before: str | None
    after: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "action": self.action,
            "before_bytes": len((self.before or "").encode("utf-8")),
            "after_bytes": len((self.after or "").encode("utf-8")),
        }


@dataclass(frozen=True, slots=True)
class ApplyResult:
    success: bool
    format: str
    dry_run: bool
    change_id: str | None
    changes: tuple[FileChange, ...] = ()
    failures: tuple[ApplyFailure, ...] = ()
    reflection: str | None = None
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "format": self.format,
            "dry_run": self.dry_run,
            "change_id": self.change_id,
            "changes": [c.to_dict() for c in self.changes],
            "failures": [f.to_dict() for f in self.failures],
            "reflection": self.reflection,
            "errors": list(self.errors),
        }


@dataclass(frozen=True, slots=True)
class ShellResult:
    success: bool
    command: str
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool = False
    needs_approval: bool = False
    cwd: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChangeRecord:
    change_id: str
    changes: list[FileChange] = field(default_factory=list)
