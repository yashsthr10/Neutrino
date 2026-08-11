"""Rule-based (+ optional chat-model) decision extraction from assistant messages."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Protocol

from src.context.runtime.conversation_context import Decision, DecisionCategory, Message


# Temporary local seam — replace with system-wide chat-model port when it exists.
class ChatModelPort(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


_TRIGGERS: list[tuple[DecisionCategory, re.Pattern[str]]] = [
    (
        "architecture",
        re.compile(r"\b(?:we'll use|we will use|decided to use|going with)\b(.+)", re.I),
    ),
    ("architecture", re.compile(r"\b(?:architecture decision|we'll adopt)\b[:\s]*(.+)", re.I)),
    (
        "coding_preference",
        re.compile(r"\b(?:the convention here is|prefer|instead of .+?, use)\b(.+)", re.I),
    ),
    ("coding_preference", re.compile(r"\b(?:coding preference|style guide)\b[:\s]*(.+)", re.I)),
    ("plan", re.compile(r"\b(?:plan(?:ned)?(?: to)?|next steps?(?: are)?)\b[:\s]*(.+)", re.I)),
    ("constraint", re.compile(r"\b(?:must not|constraint|we cannot|hard limit)\b[:\s]*(.+)", re.I)),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DecisionExtractor:
    def __init__(
        self, chat_model: ChatModelPort | None = None, *, llm_enabled: bool = False
    ) -> None:
        self.chat_model = chat_model
        self.llm_enabled = llm_enabled
        self.last_degraded: bool = False
        self.last_reason: str | None = None
        self.last_llm_invoked: bool = False

    def extract(self, message: Message) -> list[Decision]:
        self.last_degraded = False
        self.last_reason = None
        self.last_llm_invoked = False

        if message.role != "assistant":
            return []

        decisions = self._rule_based(message)

        if self.llm_enabled and self.chat_model is not None:
            try:
                self.last_llm_invoked = True
                llm_decisions = self._llm_extract(message)
                decisions = self._merge(decisions, llm_decisions)
            except Exception:
                self.last_degraded = True
                self.last_reason = "extractor_llm_unavailable"

        return decisions

    def _rule_based(self, message: Message) -> list[Decision]:
        out: list[Decision] = []
        for sentence in re.split(r"[.!?\n]+", message.content):
            sentence = sentence.strip()
            if not sentence:
                continue
            for category, pattern in _TRIGGERS:
                m = pattern.search(sentence)
                if m:
                    statement = sentence.strip()
                    out.append(
                        Decision(
                            id=str(uuid.uuid4()),
                            category=category,
                            statement=statement,
                            source_message_id=message.id,
                            created_at=_now_iso(),
                            confidence=0.7,
                        )
                    )
                    break
        return out

    def _llm_extract(self, message: Message) -> list[Decision]:
        assert self.chat_model is not None
        prompt = (
            "Extract architecture/coding_preference/plan/constraint decisions from this "
            f"assistant message as one decision per line starting with CATEGORY: ...\n\n{message.content}"
        )
        text = self.chat_model.complete(
            [
                {"role": "system", "content": "You extract decisions."},
                {"role": "user", "content": prompt},
            ]
        )
        out: list[Decision] = []
        for line in text.splitlines():
            line = line.strip()
            if ":" not in line:
                continue
            cat_raw, statement = line.split(":", 1)
            cat = cat_raw.strip().lower().replace(" ", "_")
            if cat not in ("architecture", "coding_preference", "plan", "constraint"):
                continue
            out.append(
                Decision(
                    id=str(uuid.uuid4()),
                    category=cat,  # type: ignore[arg-type]
                    statement=statement.strip(),
                    source_message_id=message.id,
                    created_at=_now_iso(),
                    confidence=0.85,
                )
            )
        return out

    def _merge(self, a: list[Decision], b: list[Decision]) -> list[Decision]:
        by_stmt: dict[str, Decision] = {}
        for d in a + b:
            key = d.statement.lower().strip()
            existing = by_stmt.get(key)
            if existing is None or d.confidence > existing.confidence:
                by_stmt[key] = d
        return list(by_stmt.values())
