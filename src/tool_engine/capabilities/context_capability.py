"""Context capabilities → ContextManagerPort."""

from __future__ import annotations

from typing import Any

from src.context.models import ContextPackage, ContextRequest
from src.tool_engine.capabilities.base import CapabilityBase
from src.tool_engine.models import ToolResult


class ContextCapability(CapabilityBase):
    def as_handler_map(self) -> dict[str, Any]:
        return {
            "context.resolve": self.resolve,
            "context.expand": self.expand,
            "context.refresh": self.refresh,
        }

    def resolve(
        self,
        *,
        task_description: str,
        task_complexity: str = "MEDIUM",
        requesting_agent: str = "planner",
        file_hints: list[str] | None = None,
        symbol_hints: list[str] | None = None,
        conversation_query: str | None = None,
        token_budget: int | None = None,
        session_id: str | None = None,
    ) -> ToolResult:
        cm = self.require_context()
        request = ContextRequest(
            task_description=task_description,
            task_complexity=task_complexity,  # type: ignore[arg-type]
            requesting_agent=requesting_agent,  # type: ignore[arg-type]
            file_hints=tuple(file_hints or ()),
            symbol_hints=tuple(symbol_hints or ()),
            conversation_query=conversation_query,
            token_budget=token_budget,
            session_id=session_id or self.session_id(),
        )
        result = cm.resolve(request)
        return self.serializer.serialize(result)

    def expand(
        self,
        *,
        package: dict[str, Any] | None = None,
        task_description: str,
        task_complexity: str = "MEDIUM",
        requesting_agent: str = "planner",
        file_hints: list[str] | None = None,
        symbol_hints: list[str] | None = None,
        token_budget: int | None = None,
        session_id: str | None = None,
        **_: Any,
    ) -> ToolResult:
        """Expand from a prior package when provided; else resolve fresh then expand noop-safe."""
        cm = self.require_context()
        sid = session_id or self.session_id()
        additional = ContextRequest(
            task_description=task_description,
            task_complexity=task_complexity,  # type: ignore[arg-type]
            requesting_agent=requesting_agent,  # type: ignore[arg-type]
            file_hints=tuple(file_hints or ()),
            symbol_hints=tuple(symbol_hints or ()),
            token_budget=token_budget,
            session_id=sid,
        )
        # LLM-facing expand: resolve additional request; if a prior package dict is passed
        # without a live object, fall back to resolve (host can pass package via orchestrator later).
        if package is None:
            result = cm.resolve(additional)
            return self.serializer.serialize(result)
        # Prefer resolve-then-expand when package cannot be reconstituted; host integrations
        # that hold ContextPackage should call ContextManager.expand directly.
        base = cm.resolve(
            ContextRequest(
                task_description=str(package.get("task_description") or task_description),
                task_complexity=task_complexity,  # type: ignore[arg-type]
                requesting_agent=requesting_agent,  # type: ignore[arg-type]
                session_id=sid,
            )
        )
        if not isinstance(base.data, ContextPackage):
            return self.serializer.serialize(base)
        result = cm.expand(base.data, additional=additional)
        return self.serializer.serialize(result)

    def refresh(
        self,
        *,
        task_description: str | None = None,
        task_complexity: str = "MEDIUM",
        requesting_agent: str = "planner",
        file_hints: list[str] | None = None,
        symbol_hints: list[str] | None = None,
        session_id: str | None = None,
        **_: Any,
    ) -> ToolResult:
        cm = self.require_context()
        # Refresh without a live package: invalidate + resolve with hints.
        cm.invalidate(scope=(file_hints[0] if file_hints else None))
        if not task_description:
            task_description = "refresh context"
        request = ContextRequest(
            task_description=task_description,
            task_complexity=task_complexity,  # type: ignore[arg-type]
            requesting_agent=requesting_agent,  # type: ignore[arg-type]
            file_hints=tuple(file_hints or ()),
            symbol_hints=tuple(symbol_hints or ()),
            session_id=session_id or self.session_id(),
        )
        result = cm.resolve(request)
        return self.serializer.serialize(result)
