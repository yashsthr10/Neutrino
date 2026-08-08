"""ToolSpec definitions for task/todo checklist tracking."""

from __future__ import annotations

from src.tool_engine.models import ToolParam, ToolSpec

# Todos are informational bookkeeping for multi-step tasks — available in every
# working phase. They do not gate FSM transitions; the WorkflowController remains
# the sole authority for phase changes.
_STATES = frozenset({"PLAN", "CONTEXT", "EXECUTE", "VERIFY", "REVIEW"})


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
