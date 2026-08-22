"""FakeContextManager / FakeConversationManager test doubles."""

from __future__ import annotations

from datetime import datetime, timezone

from src.context.models import (
    ContextMeta,
    ContextPackage,
    ContextRequest,
    ContextResult,
)
from src.context.runtime.conversation_context import (
    ConversationContext,
    ConversationSummary,
    Decision,
    DecisionCategory,
    Message,
    MessageRole,
)
from src.context.runtime.repository_context import RepositoryContext


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeConversationManager:
    """Scripted ConversationManagerPort — in-memory, no SQLite."""

    def __init__(self, session_id: str = "fake-session") -> None:
        self.session_id = session_id
        self.messages: list[Message] = []
        self.decisions: list[Decision] = []
        self.summary: ConversationSummary | None = None
        self.call_counts: dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.call_counts[name] = self.call_counts.get(name, 0) + 1

    def append(self, message: Message) -> None:
        self._count("append")
        self.messages.append(message)

    def summarize(self, *, force: bool = False) -> ContextResult[ConversationSummary]:
        self._count("summarize")
        if self.summary is None:
            text = " | ".join(f"{m.role}: {m.content[:80]}" for m in self.messages[:8])
            covers = self.messages[-1].id if self.messages else ""
            self.summary = ConversationSummary(
                text=text,
                covers_through_message_id=covers,
                created_at=_now_iso(),
                tokens_estimate=max(1, len(text.split())) if text else 0,
            )
        return ContextResult(
            data=self.summary,
            meta=ContextMeta(
                cost_ms=0.0,
                cache_hit=False,
                truncated=False,
                degraded=True,
                reason="no_chat_model_configured",
                tokens_estimate=self.summary.tokens_estimate,
                sources=("conversation",),
            ),
        )

    def retrieve(self, query: str, *, limit: int = 10) -> ContextResult[list[Message]]:
        self._count("retrieve")
        q = query.lower()
        hits = [m for m in self.messages if q in m.content.lower()][:limit]
        return ContextResult(
            data=hits,
            meta=ContextMeta(
                cost_ms=0.0,
                cache_hit=False,
                truncated=len(hits) >= limit,
                sources=("conversation",),
            ),
        )

    def get_decisions(
        self, *, category: DecisionCategory | None = None, limit: int = 20
    ) -> ContextResult[list[Decision]]:
        self._count("get_decisions")
        data = self.decisions
        if category:
            data = [d for d in data if d.category == category]
        return ContextResult(
            data=list(data)[:limit],
            meta=ContextMeta(
                cost_ms=0.0, cache_hit=False, truncated=False, sources=("conversation",)
            ),
        )

    def get_recent(
        self, *, n: int = 20, roles: tuple[MessageRole, ...] | None = None
    ) -> ContextResult[list[Message]]:
        self._count("get_recent")
        msgs = self.messages
        if roles:
            msgs = [m for m in msgs if m.role in roles]
        return ContextResult(
            data=list(msgs[-n:]),
            meta=ContextMeta(
                cost_ms=0.0, cache_hit=False, truncated=False, sources=("conversation",)
            ),
        )

    def clear(self, *, keep_decisions: bool = True) -> None:
        self._count("clear")
        self.messages.clear()
        self.summary = None
        if not keep_decisions:
            self.decisions.clear()

    def conversation_state_hash(self) -> str:
        covers = self.summary.covers_through_message_id if self.summary else "none"
        return f"{len(self.messages)}:{covers}"

    def build_conversation_context(self, *, query: str | None = None, recent_n: int = 20):
        recent = self.messages[-recent_n:]
        relevant = []
        if query:
            relevant = self.retrieve(query, limit=10).data
        tokens = sum(max(1, len(m.content.split())) for m in recent + relevant)
        return ConversationContext(
            recent_messages=tuple(recent),
            summary=self.summary,
            relevant_history=tuple(relevant),
            decisions=tuple(self.decisions),
            tokens_estimate=tokens,
            truncated=False,
        )


class FakeContextManager:
    """Scripted ContextManagerPort — returns a canned ContextPackage."""

    def __init__(self) -> None:
        self.packages: dict[str, ContextPackage] = {}
        self.default_package: ContextPackage | None = None
        self.call_counts: dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.call_counts[name] = self.call_counts.get(name, 0) + 1

    def _empty_package(self, request: ContextRequest) -> ContextPackage:
        return ContextPackage(
            request=request,
            repository=RepositoryContext(items=(), tokens_estimate=0, truncated=False),
            conversation=ConversationContext(
                recent_messages=(),
                summary=None,
                relevant_history=(),
                decisions=(),
                tokens_estimate=0,
                truncated=False,
            ),
            tokens_estimate=0,
            token_budget=8000,
            truncated=False,
            provenance=(),
            created_at=_now_iso(),
            cache_key="fake",
        )

    def resolve(self, request: ContextRequest) -> ContextResult[ContextPackage]:
        self._count("resolve")
        pkg = self.packages.get(request.task_description) or self.default_package
        if pkg is None:
            pkg = self._empty_package(request)
        return ContextResult(
            data=pkg,
            meta=ContextMeta(
                cost_ms=0.0,
                cache_hit=True,
                truncated=pkg.truncated,
                tokens_estimate=pkg.tokens_estimate,
                sources=("cache",),
            ),
        )

    def expand(
        self, package: ContextPackage, *, additional: ContextRequest
    ) -> ContextResult[ContextPackage]:
        self._count("expand")
        return self.resolve(additional)

    def refresh(self, package: ContextPackage) -> ContextResult[ContextPackage]:
        self._count("refresh")
        return self.resolve(package.request)

    def invalidate(self, scope: str | None = None) -> None:
        self._count("invalidate")

    def cache(self, package: ContextPackage) -> None:
        self._count("cache")
        self.packages[package.request.task_description] = package

    def compose(
        self,
        *,
        repository: RepositoryContext | None = None,
        conversation: ConversationContext | None = None,
        budget: int | None = None,
    ) -> ContextResult[ContextPackage]:
        self._count("compose")
        request = ContextRequest(
            task_description="compose",
            task_complexity="MEDIUM",
            requesting_agent="planner",
        )
        pkg = ContextPackage(
            request=request,
            repository=repository
            or RepositoryContext(items=(), tokens_estimate=0, truncated=False),
            conversation=conversation
            or ConversationContext(
                recent_messages=(),
                summary=None,
                relevant_history=(),
                decisions=(),
                tokens_estimate=0,
                truncated=False,
            ),
            tokens_estimate=(repository.tokens_estimate if repository else 0)
            + (conversation.tokens_estimate if conversation else 0),
            token_budget=budget or 8000,
            truncated=False,
            provenance=(),
            created_at=_now_iso(),
            cache_key="fake-compose",
        )
        return ContextResult(
            data=pkg,
            meta=ContextMeta(
                cost_ms=0.0,
                cache_hit=False,
                truncated=False,
                tokens_estimate=pkg.tokens_estimate,
                sources=("rna", "conversation"),
            ),
        )
