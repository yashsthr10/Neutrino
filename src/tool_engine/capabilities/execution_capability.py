"""Execution capabilities — apply / diff / rollback / run via ExecutionPort."""

from __future__ import annotations

from typing import Any

from src.tool_engine.capabilities.base import CapabilityBase
from src.tool_engine.models import ToolMeta, ToolResult


class ExecutionCapability(CapabilityBase):
    def as_handler_map(self) -> dict[str, Any]:
        return {
            "executor.apply": self.apply,
            "executor.rollback": self.rollback,
            "executor.diff": self.diff,
            "executor.run": self.run,
        }

    def apply(
        self,
        *,
        patch: str = "",
        path: str | None = None,
        format: str = "auto",
        dry_run: bool = False,
        **_: Any,
    ) -> ToolResult:
        if self.services.execution is None:
            return self.serializer.not_implemented("executor.apply")
        result = self.services.execution.apply(
            patch=patch,
            path=path,
            format=format,
            dry_run=dry_run,
        )
        data = result.to_dict()
        return ToolResult(
            success=result.success,
            data=data,
            meta=ToolMeta(
                error=None if result.success else "apply_failed",
                reason=result.reflection,
                degraded=bool(result.failures),
            ),
            errors=result.errors,
        )

    def rollback(self, *, change_id: str | None = None, **_: Any) -> ToolResult:
        if self.services.execution is None:
            return self.serializer.not_implemented("executor.rollback")
        data = self.services.execution.rollback(change_id=change_id)
        ok = bool(data.get("success"))
        return ToolResult(
            success=ok,
            data=data,
            meta=ToolMeta(error=None if ok else "rollback_failed", reason=data.get("error")),
            errors=() if ok else (str(data.get("error") or "rollback_failed"),),
        )

    def diff(
        self,
        *,
        path: str | None = None,
        change_id: str | None = None,
        **_: Any,
    ) -> ToolResult:
        if self.services.execution is None:
            return self.serializer.not_implemented("executor.diff")
        data = self.services.execution.diff(path=path, change_id=change_id)
        return ToolResult(success=True, data=data, meta=ToolMeta())

    def run(
        self,
        *,
        command: str,
        approved: bool = False,
        timeout_s: float = 120.0,
        **_: Any,
    ) -> ToolResult:
        if self.services.execution is None:
            return self.serializer.not_implemented("executor.run")
        result = self.services.execution.run(
            command=command,
            approved=bool(approved),
            timeout_s=float(timeout_s),
        )
        error = None
        if result.needs_approval:
            error = "permission_denied"
        elif not result.success:
            error = "execution_error"
        return ToolResult(
            success=result.success,
            data=result.to_dict(),
            meta=ToolMeta(
                error=error,
                truncated=result.truncated,
                reason=(
                    "Shell command requires approved=true"
                    if result.needs_approval
                    else (result.stderr or None)
                ),
            ),
            errors=()
            if result.success
            else (result.stderr or "command failed",),
        )
