"""ToolSpec definitions for context.* tools."""

from __future__ import annotations

from src.tool_engine.models import ToolParam, ToolSpec

_PLAN_CTX = frozenset({"PLAN", "CONTEXT"})
_RESOLVE_STATES = frozenset({"PLAN", "CONTEXT", "EXECUTE"})
_REFRESH_STATES = frozenset({"PLAN", "CONTEXT", "EXECUTE", "VERIFY", "REVIEW"})


def context_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="context.resolve",
            description=(
                "Build a bounded context package for the current task. "
                "Requires task_description (string)."
            ),
            category="context",
            handler_key="context.resolve",
            states=_RESOLVE_STATES,
            parameters=(
                ToolParam("task_description", "string", True, "User task / goal"),
                ToolParam("task_complexity", "string", False, "SIMPLE|MEDIUM|COMPLEX", "MEDIUM"),
                ToolParam(
                    "requesting_agent",
                    "string",
                    False,
                    "planner|coder|verifier|reviewer",
                    "planner",
                ),
                ToolParam("file_hints", "array", False, "Optional file path hints"),
                ToolParam("symbol_hints", "array", False, "Optional symbol name hints"),
                ToolParam("conversation_query", "string", False, "Optional memory query"),
                ToolParam("token_budget", "integer", False, "Optional token budget override"),
                ToolParam("session_id", "string", False, "Optional session id"),
            ),
        ),
        ToolSpec(
            name="context.expand",
            description="Expand an existing context package with additional retrieval.",
            category="context",
            handler_key="context.expand",
            states=_PLAN_CTX,
            parameters=(
                ToolParam("task_description", "string", True, "Additional retrieval goal"),
                ToolParam("task_complexity", "string", False, "SIMPLE|MEDIUM|COMPLEX", "MEDIUM"),
                ToolParam(
                    "requesting_agent",
                    "string",
                    False,
                    "planner|coder|verifier|reviewer",
                    "planner",
                ),
                ToolParam("file_hints", "array", False, "Optional file path hints"),
                ToolParam("symbol_hints", "array", False, "Optional symbol name hints"),
                ToolParam("token_budget", "integer", False, "Optional token budget"),
                ToolParam("session_id", "string", False, "Optional session id"),
                ToolParam("package", "object", False, "Optional prior package summary"),
            ),
        ),
        ToolSpec(
            name="context.refresh",
            description="Invalidate cache and refresh context after repo changes.",
            category="context",
            handler_key="context.refresh",
            states=_REFRESH_STATES,
            parameters=(
                ToolParam("task_description", "string", False, "Task description for re-resolve"),
                ToolParam("task_complexity", "string", False, "SIMPLE|MEDIUM|COMPLEX", "MEDIUM"),
                ToolParam(
                    "requesting_agent",
                    "string",
                    False,
                    "planner|coder|verifier|reviewer",
                    "planner",
                ),
                ToolParam("file_hints", "array", False, "Optional file path hints"),
                ToolParam("symbol_hints", "array", False, "Optional symbol name hints"),
                ToolParam("session_id", "string", False, "Optional session id"),
            ),
        ),
    ]
