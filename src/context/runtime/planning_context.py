"""PlanningContext — plan steps and task checklist owned by the Planner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TaskStatus = Literal["pending", "in_progress", "completed", "cancelled"]


@dataclass(frozen=True, slots=True)
class PlanTask:
    """One checklist item tracked across FSM phases (set via `plan.set_tasks`)."""

    id: str
    content: str
    status: TaskStatus = "pending"


@dataclass(frozen=True, slots=True)
class PlanningContext:
    plan_steps: tuple[str, ...] = ()
    current_step: int = 0
    tasks: tuple[PlanTask, ...] = ()
