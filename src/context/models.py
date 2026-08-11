"""Context Subsystem wire-contract data models (see docs/02_api_spec.md)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Generic, TypeVar

from src.context.runtime.conversation_context import (
    ConversationContext,
    ConversationSummary,
    Decision,
    DecisionCategory,
    Message,
    MessageRole,
)
from src.context.runtime.repository_context import (
    ItemKind,
    RepositoryContext,
    RepositoryContextItem,
)
from src.context.runtime.request_context import RequestingAgent, TaskComplexity

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ContextMeta:
    cost_ms: float
    cache_hit: bool
    truncated: bool
    degraded: bool = False
    reason: str | None = None
    error: str | None = None
    tokens_estimate: int = 0
    sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ContextResult(Generic[T]):
    data: T
    meta: ContextMeta

    def to_dict(self) -> dict[str, Any]:
        return {"data": _to_jsonable(self.data), "meta": asdict(self.meta)}


def _to_jsonable(value: Any) -> Any:
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
class ContextRequest:
    task_description: str
    task_complexity: TaskComplexity
    requesting_agent: RequestingAgent
    file_hints: tuple[str, ...] = ()
    symbol_hints: tuple[str, ...] = ()
    conversation_query: str | None = None
    token_budget: int | None = None
    capabilities: tuple[str, ...] | None = None
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class ContextPackage:
    request: ContextRequest
    repository: RepositoryContext
    conversation: ConversationContext
    tokens_estimate: int
    token_budget: int
    truncated: bool
    provenance: tuple[str, ...]
    created_at: str
    cache_key: str


__all__ = [
    "ContextMeta",
    "ContextResult",
    "ContextRequest",
    "ContextPackage",
    "ConversationContext",
    "ConversationSummary",
    "Decision",
    "DecisionCategory",
    "ItemKind",
    "Message",
    "MessageRole",
    "RepositoryContext",
    "RepositoryContextItem",
    "RequestingAgent",
    "TaskComplexity",
]
