"""Git capabilities — commit / undo / diff via GitService."""

from __future__ import annotations

from typing import Any

from src.tool_engine.capabilities.base import CapabilityBase
from src.tool_engine.models import ToolMeta, ToolResult


class GitCapability(CapabilityBase):
    def as_handler_map(self) -> dict[str, Any]:
        return {
            "git.commit": self.commit,
            "git.undo": self.undo,
            "git.diff": self.diff,
        }

    def commit(self, *, message: str = "", **_: Any) -> ToolResult:
        if self.services.git is None:
            return self.serializer.not_implemented("git.commit")
        result = self.services.git.commit(message=message)
        return ToolResult(
            success=result.success,
            data=result.data,
            meta=ToolMeta(error=None if result.success else "git_error", reason=result.error),
            errors=() if result.success else (result.error or "git commit failed",),
        )

    def undo(self, **_: Any) -> ToolResult:
        if self.services.git is None:
            return self.serializer.not_implemented("git.undo")
        result = self.services.git.undo()
        return ToolResult(
            success=result.success,
            data=result.data,
            meta=ToolMeta(error=None if result.success else "git_error", reason=result.error),
            errors=() if result.success else (result.error or "git undo failed",),
        )

    def diff(self, *, staged: bool = False, path: str | None = None, **_: Any) -> ToolResult:
        if self.services.git is None:
            return self.serializer.not_implemented("git.diff")
        result = self.services.git.diff(staged=bool(staged), path=path)
        return ToolResult(
            success=result.success,
            data=result.data,
            meta=ToolMeta(error=None if result.success else "git_error", reason=result.error),
            errors=() if result.success else (result.error or "git diff failed",),
        )
