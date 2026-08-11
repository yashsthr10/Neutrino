"""ToolSpec definitions for task/todo checklist tracking."""

from __future__ import annotations

from src.tool_engine.models import ToolParam, ToolSpec

_STATES = frozenset({"AGENT", "PLAN", "CONTEXT", "EXECUTE", "VERIFY", "REVIEW"})


def planning_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="plan.set_tasks",
            description=(
                "Create or update the task checklist for this run. Use for multi-step "
                "work (3+ distinct steps): break the task down, keep exactly one item "
                "'in_progress' at a time, and mark items 'completed' the moment they are "
                "done. Always pass the FULL current list, not a partial diff."
            ),
            category="planning",
            handler_key="plan.set_tasks",
            states=_STATES,
            when_to_use="Multi-step work (3+ distinct steps) where progress visibility helps.",
            when_not_to_use="Small single-step asks — skip the checklist.",
            pairs_with=("executor.apply", "context.resolve"),
            parameters=(
                ToolParam(
                    "tasks",
                    "array",
                    True,
                    "Full checklist: objects with 'content' (string, required), "
                    "optional 'id', optional 'status' "
                    "(pending|in_progress|completed|cancelled, default pending).",
                    item_type="object",
                ),
            ),
        ),
    ]
