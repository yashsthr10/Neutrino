"""RetrievalPlanner — execute RetrievalPlan against RNA + Conversation Manager."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Protocol

from src.context.config import ContextConfig
from src.context.manager.analyzer import RetrievalPlan
from src.context.models import ContextRequest
from src.context.runtime.conversation_context import ConversationContext
from src.rna.models import RnaResult


class _ConversationPort(Protocol):
    def build_conversation_context(self, *, query: str | None = None, recent_n: int = 20): ...


class RetrievalPlanner:
    def __init__(
        self,
        rna: Any,
        conversation: _ConversationPort,
        config: ContextConfig,
    ) -> None:
        self.rna = rna
        self.conversation = conversation
        self.config = config
        self.last_rna_calls: int = 0
        self.last_conversation_calls: int = 0
        self.last_degraded: bool = False
        self.last_reason: str | None = None

    def execute(
        self, plan: RetrievalPlan, request: ContextRequest
    ) -> tuple[list[tuple[str, RnaResult]], ConversationContext]:
        self.last_rna_calls = 0
        self.last_conversation_calls = 0
        self.last_degraded = False
        self.last_reason = None

        unique_calls = self._dedupe(plan.calls)
        timeout_s = self.config.retrieval_timeout_ms / 1000.0

        rna_results: list[tuple[str, RnaResult]] = []
        conversation_ctx: ConversationContext | None = None

        def run_rna() -> list[tuple[str, RnaResult]]:
            out: list[tuple[str, RnaResult]] = []
            for method_name, kwargs in unique_calls:
                try:
                    method = getattr(self.rna, method_name)
                    result = method(**{k: v for k, v in kwargs.items() if v is not None})
                    out.append((method_name, result))
                except Exception as exc:
                    self.last_degraded = True
                    self.last_reason = f"rna_call_failed:{method_name}:{exc}"
            return out

        def run_conversation() -> ConversationContext:
            if not plan.query_conversation:
                return ConversationContext(
                    recent_messages=(),
                    summary=None,
                    relevant_history=(),
                    decisions=(),
                    tokens_estimate=0,
                    truncated=False,
                )
            query = request.conversation_query or request.task_description
            return self.conversation.build_conversation_context(query=query)

        with ThreadPoolExecutor(max_workers=2) as pool:
            rna_fut = pool.submit(run_rna)
            conv_fut = pool.submit(run_conversation)
            try:
                rna_results = rna_fut.result(timeout=timeout_s * max(1, len(unique_calls) or 1))
            except FuturesTimeout:
                self.last_degraded = True
                self.last_reason = "rna_unavailable"
                rna_results = []
            except Exception:
                self.last_degraded = True
                self.last_reason = "rna_unavailable"
                rna_results = []
            try:
                conversation_ctx = conv_fut.result(timeout=timeout_s)
            except Exception:
                conversation_ctx = ConversationContext(
                    recent_messages=(),
                    summary=None,
                    relevant_history=(),
                    decisions=(),
                    tokens_estimate=0,
                    truncated=False,
                )

        self.last_rna_calls = len(unique_calls)
        self.last_conversation_calls = 1 if plan.query_conversation else 0
        return rna_results, conversation_ctx

    def _dedupe(self, calls: tuple[tuple[str, dict], ...]) -> list[tuple[str, dict]]:
        seen: set[str] = set()
        out: list[tuple[str, dict]] = []
        for method, kwargs in calls:
            key = method + ":" + json.dumps(kwargs, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            out.append((method, kwargs))
        return out
