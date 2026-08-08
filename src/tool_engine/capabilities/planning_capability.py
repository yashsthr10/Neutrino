"""Planning capability — validates and normalizes the task checklist."""

from __future__ import annotations

from typing import Any

from src.tool_engine.capabilities.base import CapabilityBase
from src.tool_engine.models import ToolResult

_VALID_STATUSES = frozenset({"pending", "in_progress", "completed", "cancelled"})


class PlanningCapability(CapabilityBase):
    def as_handler_map(self) -> dict[str, Any]:
        return {"plan.set_tasks": self.set_tasks}

    def set_tasks(self, *, tasks: list | None = None, **_: Any) -> ToolResult:
        if not isinstance(tasks, list) or not tasks:
            return self.serializer.from_exception(
                "tasks must be a non-empty array of {content, status?} objects",
                error_code="validation_error",
            )
        normalized: list[dict[str, str]] = []
        for index, raw in enumerate(tasks):
            if not isinstance(raw, dict):
                return self.serializer.from_exception(
                    f"tasks[{index}] must be an object",
                    error_code="validation_error",
                )
            content = str(raw.get("content") or "").strip()
            if not content:
                return self.serializer.from_exception(
                    f"tasks[{index}].content is required",
                    error_code="validation_error",
                )
            status = str(raw.get("status") or "pending").strip().lower()
            if status not in _VALID_STATUSES:
                status = "pending"
            task_id = str(raw.get("id") or index + 1)
            normalized.append({"id": task_id, "content": content, "status": status})
        return ToolResult(success=True, data={"tasks": normalized})
