"""ExecutionContext — immutable runtime state container for one execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from src.context.runtime.conversation_context import ConversationContext
from src.context.runtime.event_log import EventLog
from src.context.runtime.execution_state import ExecutionState
from src.context.runtime.metrics_context import MetricsContext
from src.context.runtime.planning_context import PlanningContext
from src.context.runtime.repository_context import RepositoryContext
from src.context.runtime.request_context import RequestContext
from src.context.runtime.verification_context import VerificationContext


def _to_jsonable(value: Any) -> Any:
    # Mirrors src/rna/models.py::_to_jsonable — keep in sync if either changes.
    if isinstance(value, tuple):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {k: _to_jsonable(getattr(value, k)) for k in value.__dataclass_fields__}
    return value


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    request: RequestContext
    repository: RepositoryContext | None = None
    conversation: ConversationContext | None = None
    planning: PlanningContext = field(default_factory=PlanningContext)
    execution: ExecutionState = field(default_factory=ExecutionState)
    verification: VerificationContext = field(default_factory=VerificationContext)
    metrics: MetricsContext = field(default_factory=MetricsContext)
    events: EventLog = field(default_factory=EventLog)
    version: int = 0

    def with_repository(self, repository: RepositoryContext) -> ExecutionContext:
        return replace(self, repository=repository, version=self.version + 1)

    def with_conversation(self, conversation: ConversationContext) -> ExecutionContext:
        return replace(self, conversation=conversation, version=self.version + 1)

    def with_planning(self, planning: PlanningContext) -> ExecutionContext:
        return replace(self, planning=planning, version=self.version + 1)

    def with_execution(self, execution: ExecutionState) -> ExecutionContext:
        return replace(self, execution=execution, version=self.version + 1)

    def with_verification(self, verification: VerificationContext) -> ExecutionContext:
        return replace(self, verification=verification, version=self.version + 1)

    def with_metrics(self, metrics: MetricsContext) -> ExecutionContext:
        return replace(self, metrics=metrics, version=self.version + 1)

    def with_event(self, kind: str, payload: dict) -> ExecutionContext:
        return replace(self, events=self.events.append(kind, payload), version=self.version + 1)

    def checkpoint(self) -> ExecutionContext:
        """Identity — the object *is* the checkpoint (call-site readability)."""
        return self

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)
