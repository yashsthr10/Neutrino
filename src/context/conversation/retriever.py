"""Ranked retrieval over message store + memory index."""

from __future__ import annotations

from src.context.conversation.memory_index import MemoryIndex
from src.context.conversation.message_store import MessageStore
from src.context.runtime.conversation_context import Decision, Message


class Retriever:
    def __init__(self, store: MessageStore, index: MemoryIndex) -> None:
        self.store = store
        self.index = index

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 10,
        decisions: list[Decision] | None = None,
    ) -> list[Message]:
        hits = self.index.search(query, limit=limit * 3)
        decision_ids = {d.source_message_id for d in (decisions or [])}
        by_id = {m.id: m for m in self.store.get_all()}

        scored: list[tuple[float, Message]] = []
        for msg_id, kw_score in hits:
            msg = by_id.get(msg_id)
            if msg is None:
                continue
            score = kw_score
            if msg_id in decision_ids:
                score += 0.25
            # Recency: later messages get a small boost
            all_ids = list(by_id.keys())
            if msg_id in all_ids:
                score += 0.1 * (all_ids.index(msg_id) / max(1, len(all_ids) - 1))
            scored.append((score, msg))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]
