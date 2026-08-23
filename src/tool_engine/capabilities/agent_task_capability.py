"""agent.task capability."""

from __future__ import annotations

from typing import Any

from src.tool_engine.capabilities.base import CapabilityBase
from src.tool_engine.models import ToolResult


class AgentTaskCapability(CapabilityBase):
    def as_handler_map(self) -> dict[str, Any]:
        return {"agent.task": self.task}

    def task(
        self,
        *,
        prompt: str,
        scope: str | None = None,
    ) -> ToolResult:
        from src.agent.subagent import run_subagent

        inference = getattr(self.services, "inference", None)
        engine = getattr(self.services, "engine", None)
        if inference is None or engine is None:
            return self.serializer.from_exception(
                "Subagent requires inference and ToolEngine on RuntimeServices",
                error_code="not_implemented",
            )
        ctx = getattr(self.services, "execution_context", None)
        summary = run_subagent(
            inference=inference,
            tool_engine=engine,
            prompt=prompt,
            scope=scope,
            execution_context=ctx,
        )
        return self.serializer.serialize(summary)
