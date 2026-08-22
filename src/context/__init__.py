"""Context Subsystem — composition, conversation memory, and runtime state."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.context.bootstrap import build_context_subsystem, build_context_subsystem_with_inference
from src.context.config import ContextConfig
from src.context.conversation.conversation_manager import ConversationManager
from src.context.errors import ContextConfigError, ContextError, ContextSecurityError
from src.context.manager.context_manager import ContextManager
from src.context.models import (
    ContextMeta,
    ContextPackage,
    ContextRequest,
    ContextResult,
    ConversationContext,
    ConversationSummary,
    Decision,
    DecisionCategory,
    Message,
    MessageRole,
    RepositoryContext,
    RepositoryContextItem,
    RequestingAgent,
    TaskComplexity,
)
from src.context.runtime.execution_context import ExecutionContext
from src.context.runtime.execution_state import ExecutionState
from src.context.runtime.metrics_context import MetricsContext
from src.context.runtime.planning_context import PlanningContext
from src.context.runtime.request_context import RequestContext
from src.context.runtime.verification_context import VerificationContext


@runtime_checkable
class ContextManagerPort(Protocol):
    """Composes a bounded, ranked context package for one agent step. Never calls an LLM."""

    def resolve(self, request: ContextRequest) -> ContextResult[ContextPackage]: ...

    def expand(
        self, package: ContextPackage, *, additional: ContextRequest
    ) -> ContextResult[ContextPackage]: ...

    def refresh(self, package: ContextPackage) -> ContextResult[ContextPackage]: ...

    def invalidate(self, scope: str | None = None) -> None: ...

    def cache(self, package: ContextPackage) -> None: ...

    def compose(
        self,
        *,
        repository: RepositoryContext | None = None,
        conversation: ConversationContext | None = None,
        budget: int | None = None,
    ) -> ContextResult[ContextPackage]: ...


@runtime_checkable
class ConversationManagerPort(Protocol):
    """Owns conversational memory for one session. No repository knowledge, no RNA dependency."""

    def append(self, message: Message) -> None: ...

    def summarize(self, *, force: bool = False) -> ContextResult[ConversationSummary]: ...

    def retrieve(self, query: str, *, limit: int = 10) -> ContextResult[list[Message]]: ...

    def get_decisions(
        self, *, category: DecisionCategory | None = None, limit: int = 20
    ) -> ContextResult[list[Decision]]: ...

    def get_recent(
        self, *, n: int = 20, roles: tuple[MessageRole, ...] | None = None
    ) -> ContextResult[list[Message]]: ...

    def clear(self, *, keep_decisions: bool = True) -> None: ...


__all__ = [
    "ContextManager",
    "ContextManagerPort",
    "ConversationManager",
    "ConversationManagerPort",
    "ExecutionContext",
    "ContextConfig",
    "ContextError",
    "ContextSecurityError",
    "ContextConfigError",
    "ContextResult",
    "ContextMeta",
    "ContextRequest",
    "ContextPackage",
    "ConversationContext",
    "ConversationSummary",
    "Decision",
    "DecisionCategory",
    "Message",
    "MessageRole",
    "RepositoryContext",
    "RepositoryContextItem",
    "RequestContext",
    "RequestingAgent",
    "TaskComplexity",
    "PlanningContext",
    "ExecutionState",
    "VerificationContext",
    "MetricsContext",
    "build_context_subsystem",
    "build_context_subsystem_with_inference",
]
