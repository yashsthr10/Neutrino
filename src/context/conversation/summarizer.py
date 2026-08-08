"""Rolling conversation summarization via chat-model port (with naive fallback)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from src.context.runtime.conversation_context import ConversationSummary, Message


class ChatModelPort(Protocol):
    """Temporary local seam. Replace with the system-wide chat-model port
    (docs/02_specs.md S10) as soon as it exists — same method shape assumed,
    this Protocol is deleted, not extended, on that day."""

    def complete(self, messages: list[dict[str, str]]) -> str: ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


class Summarizer:
    def __init__(self, chat_model: ChatModelPort | None = None) -> None:
        self.chat_model = chat_model
        self.last_degraded: bool = False
        self.last_reason: str | None = None
        self.last_llm_invoked: bool = False

    def summarize(
        self,
        messages: list[Message],
        *,
        previous: ConversationSummary | None = None,
    ) -> ConversationSummary:
        self.last_degraded = False
        self.last_reason = None
        self.last_llm_invoked = False

        if not messages:
            text = previous.text if previous else ""
            covers = previous.covers_through_message_id if previous else ""
            return ConversationSummary(
                text=text,
                covers_through_message_id=covers,
                created_at=_now_iso(),
                tokens_estimate=_estimate_tokens(text) if text else 0,
            )

        covers = messages[-1].id

        if self.chat_model is None:
            self.last_degraded = True
            self.last_reason = "no_chat_model_configured"
            return self._naive(messages, previous, covers)

        try:
            self.last_llm_invoked = True
            prior = previous.text if previous else ""
            joined = "\n".join(f"{m.role}: {m.content}" for m in messages)
            prompt = (
                "Update this rolling conversation summary.\n"
                f"Previous summary:\n{prior}\n\nNew messages:\n{joined}\n\n"
                "Return a concise updated summary."
            )
            text = self.chat_model.complete(
                [
                    {"role": "system", "content": "You summarize conversations."},
                    {"role": "user", "content": prompt},
                ]
            ).strip()
            return ConversationSummary(
                text=text,
                covers_through_message_id=covers,
                created_at=_now_iso(),
                tokens_estimate=_estimate_tokens(text),
            )
        except Exception:
            self.last_degraded = True
            self.last_reason = "summarizer_unavailable"
            return self._naive(messages, previous, covers)

    def _naive(
        self,
        messages: list[Message],
        previous: ConversationSummary | None,
        covers: str,
    ) -> ConversationSummary:
        chunks: list[str] = []
        if previous and previous.text:
            chunks.append(previous.text)
        for m in messages[:8]:
            chunks.append(f"{m.role}: {m.content[:200]}")
        text = " | ".join(chunks)[:2000]
        return ConversationSummary(
            text=text,
            covers_through_message_id=covers,
            created_at=_now_iso(),
            tokens_estimate=_estimate_tokens(text),
        )
