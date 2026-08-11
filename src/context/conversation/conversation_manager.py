"""ConversationManager — owns conversational memory for one session."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from src.context.config import ContextConfig
from src.context.conversation.decision_extractor import DecisionExtractor
from src.context.conversation.memory_index import MemoryIndex
from src.context.conversation.message_store import MessageStore
from src.context.conversation.retriever import Retriever
from src.context.conversation.summarizer import ChatModelPort, Summarizer
from src.context.models import ContextMeta, ContextResult
from src.context.observability import timed_call
from src.context.runtime.conversation_context import (
    ConversationSummary,
    Decision,
    DecisionCategory,
    Message,
    MessageRole,
)


class ConversationManager:
    """Owns conversational memory. No repository knowledge, no RNA dependency."""

    def __init__(
        self,
        session_id: str,
        config: ContextConfig | None = None,
        *,
        chat_model: ChatModelPort | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.session_id = session_id
        self.config = config or ContextConfig()
        base = cache_dir or self.config.resolved_cache_dir()
        session_dir = base / "conversation" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        (
            (base / ".gitignore").write_text("*\n", encoding="utf-8")
            if not (base / ".gitignore").exists()
            else None
        )

        self._store = MessageStore(session_dir / "messages.sqlite", session_id)
        self._index = MemoryIndex(session_dir / "memory_index" / "keyword.sqlite", session_id)
        self._decisions_db = session_dir / "decisions.sqlite"
        self._summaries_db = session_dir / "summaries.sqlite"
        self._lock = threading.Lock()
        self._extractor = DecisionExtractor(
            chat_model,
            llm_enabled=self.config.decision_extraction_llm_enabled,
        )
        self._summarizer = Summarizer(chat_model)
        self._retriever = Retriever(self._store, self._index)
        self._ensure_decision_schema()
        self._ensure_summary_schema()

    def _ensure_decision_schema(self) -> None:
        with sqlite3.connect(str(self._decisions_db)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    source_message_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    confidence REAL NOT NULL
                )
                """
            )
            conn.commit()

    def _ensure_summary_schema(self) -> None:
        with sqlite3.connect(str(self._summaries_db)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS summaries (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    covers_through_message_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    tokens_estimate INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def append(self, message: Message) -> None:
        with timed_call("append", f"role={message.role}") as log:
            with self._lock:
                stored = self._store.append(message)
                self._index.index_message(stored)
                if stored.role == "assistant":
                    for d in self._extractor.extract(stored):
                        self._persist_decision(d)
                covers = self._latest_summary()
                covers_id = covers.covers_through_message_id if covers else None
                backlog = self._store.unsummarized_token_count(covers_id)
                if backlog >= self.config.summarization_trigger_tokens:
                    self._run_summarize(force=False)
                log.llm_invoked = self._extractor.last_llm_invoked

    def summarize(self, *, force: bool = False) -> ContextResult[ConversationSummary]:
        with timed_call("summarize", f"force={force}") as log:
            summary = self._run_summarize(force=force)
            degraded = self._summarizer.last_degraded
            reason = self._summarizer.last_reason
            log.degraded = degraded
            log.llm_invoked = self._summarizer.last_llm_invoked
            log.tokens_estimate = summary.tokens_estimate
            return ContextResult(
                data=summary,
                meta=ContextMeta(
                    cost_ms=0.0,
                    cache_hit=False,
                    truncated=False,
                    degraded=degraded,
                    reason=reason,
                    tokens_estimate=summary.tokens_estimate,
                    sources=("conversation",),
                ),
            )

    def retrieve(self, query: str, *, limit: int = 10) -> ContextResult[list[Message]]:
        with timed_call("retrieve", f"query={query[:80]}") as log:
            decisions = self._load_decisions(None, 100)
            msgs = self._retriever.retrieve(query, limit=limit, decisions=decisions)
            log.tokens_estimate = sum(max(1, len(m.content.split())) for m in msgs)
            return ContextResult(
                data=msgs,
                meta=ContextMeta(
                    cost_ms=0.0,
                    cache_hit=False,
                    truncated=len(msgs) >= limit,
                    tokens_estimate=log.tokens_estimate,
                    sources=("conversation",),
                ),
            )

    def get_decisions(
        self, *, category: DecisionCategory | None = None, limit: int = 20
    ) -> ContextResult[list[Decision]]:
        with timed_call("get_decisions", f"category={category}"):
            data = self._load_decisions(category, limit)
            return ContextResult(
                data=data,
                meta=ContextMeta(
                    cost_ms=0.0,
                    cache_hit=False,
                    truncated=len(data) >= limit,
                    sources=("conversation",),
                ),
            )

    def get_recent(
        self, *, n: int = 20, roles: tuple[MessageRole, ...] | None = None
    ) -> ContextResult[list[Message]]:
        with timed_call("get_recent", f"n={n}"):
            data = self._store.get_recent(n, roles=roles)
            return ContextResult(
                data=data,
                meta=ContextMeta(
                    cost_ms=0.0,
                    cache_hit=False,
                    truncated=False,
                    sources=("conversation",),
                ),
            )

    def clear(self, *, keep_decisions: bool = True) -> None:
        with timed_call("clear", f"keep_decisions={keep_decisions}"):
            with self._lock:
                self._store.clear()
                self._index.clear()
                with sqlite3.connect(str(self._summaries_db)) as conn:
                    conn.execute("DELETE FROM summaries WHERE session_id=?", (self.session_id,))
                    conn.commit()
                if not keep_decisions:
                    with sqlite3.connect(str(self._decisions_db)) as conn:
                        conn.execute("DELETE FROM decisions WHERE session_id=?", (self.session_id,))
                        conn.commit()

    def conversation_state_hash(self) -> str:
        msgs = self._store.get_all()
        summary = self._latest_summary()
        summary_id = summary.covers_through_message_id if summary else "none"
        return f"{len(msgs)}:{summary_id}"

    def build_conversation_context(self, *, query: str | None = None, recent_n: int = 20):
        from src.context.runtime.conversation_context import ConversationContext

        recent = self._store.get_recent(recent_n)
        summary = self._latest_summary()
        decisions = self._load_decisions(None, 20)
        relevant: list[Message] = []
        if query:
            relevant = self._retriever.retrieve(query, limit=10, decisions=decisions)
        tokens = sum(max(1, len(m.content.split())) for m in recent + relevant)
        if summary:
            tokens += summary.tokens_estimate
        tokens += sum(max(1, len(d.statement.split())) for d in decisions)
        return ConversationContext(
            recent_messages=tuple(recent),
            summary=summary,
            relevant_history=tuple(relevant),
            decisions=tuple(decisions),
            tokens_estimate=tokens,
            truncated=False,
        )

    def _run_summarize(self, *, force: bool) -> ConversationSummary:
        previous = self._latest_summary()
        covers_id = previous.covers_through_message_id if previous else None
        new_msgs = self._store.get_after(covers_id)
        if not force and not new_msgs:
            return previous or ConversationSummary(
                text="",
                covers_through_message_id="",
                created_at="",
                tokens_estimate=0,
            )
        summary = self._summarizer.summarize(new_msgs, previous=previous)
        self._persist_summary(summary)
        return summary

    def _persist_decision(self, d: Decision) -> None:
        with sqlite3.connect(str(self._decisions_db)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO decisions
                (id, session_id, category, statement, source_message_id, created_at, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d.id,
                    self.session_id,
                    d.category,
                    d.statement,
                    d.source_message_id,
                    d.created_at,
                    d.confidence,
                ),
            )
            conn.commit()

    def _persist_summary(self, s: ConversationSummary) -> None:
        import uuid

        with sqlite3.connect(str(self._summaries_db)) as conn:
            conn.execute(
                """
                INSERT INTO summaries
                (id, session_id, text, covers_through_message_id, created_at, tokens_estimate)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    self.session_id,
                    s.text,
                    s.covers_through_message_id,
                    s.created_at,
                    s.tokens_estimate,
                ),
            )
            conn.commit()

    def _latest_summary(self) -> ConversationSummary | None:
        with sqlite3.connect(str(self._summaries_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM summaries WHERE session_id=?
                ORDER BY created_at DESC LIMIT 1
                """,
                (self.session_id,),
            ).fetchone()
        if row is None:
            return None
        return ConversationSummary(
            text=row["text"],
            covers_through_message_id=row["covers_through_message_id"],
            created_at=row["created_at"],
            tokens_estimate=row["tokens_estimate"],
        )

    def _load_decisions(self, category: DecisionCategory | None, limit: int) -> list[Decision]:
        with sqlite3.connect(str(self._decisions_db)) as conn:
            conn.row_factory = sqlite3.Row
            if category:
                rows = conn.execute(
                    """
                    SELECT * FROM decisions WHERE session_id=? AND category=?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (self.session_id, category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM decisions WHERE session_id=?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (self.session_id, limit),
                ).fetchall()
        return [
            Decision(
                id=r["id"],
                category=r["category"],
                statement=r["statement"],
                source_message_id=r["source_message_id"],
                created_at=r["created_at"],
                confidence=r["confidence"],
            )
            for r in rows
        ]
