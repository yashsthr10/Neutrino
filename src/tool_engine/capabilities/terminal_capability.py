"""Terminal capabilities — full shell access via ExecutionPort."""

from __future__ import annotations

from typing import Any

from src.tool_engine.capabilities.base import CapabilityBase
from src.tool_engine.models import ToolMeta, ToolResult


class TerminalCapability(CapabilityBase):
    def as_handler_map(self) -> dict[str, Any]:
        return {
            "terminal.run": self.run,
        }

    def run(
        self,
        *,
        command: str,
        approved: bool = False,
        timeout_s: float = 600.0,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
        **_: Any,
    ) -> ToolResult:
        if self.services.execution is None:
            return self.serializer.not_implemented("terminal.run")
        result = self.services.execution.terminal(
            command=command,
            approved=bool(approved),
            timeout_s=float(timeout_s),
            cwd=cwd,
            env=env,
            stdin=stdin,
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
            errors=() if result.success else (result.stderr or "command failed",),
        )
