"""Structured per-call logging for the Context Subsystem (mirrors rna/observability.py)."""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger("context")


@dataclass
class CallLog:
    method: str
    params_summary: str
    cost_ms: float = 0.0
    cache_hit: bool = False
    truncated: bool = False
    degraded: bool = False
    error: str | None = None
    tokens_estimate: int = 0
    sources: tuple[str, ...] = ()
    llm_invoked: bool = False
    requesting_agent: str | None = None
    task_complexity: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def emit(self) -> None:
        payload: dict[str, Any] = {
            "method": self.method,
            "params_summary": self.params_summary,
            "cost_ms": self.cost_ms,
            "cache_hit": self.cache_hit,
            "truncated": self.truncated,
            "degraded": self.degraded,
            "tokens_estimate": self.tokens_estimate,
            "sources": list(self.sources),
        }
        if self.requesting_agent:
            payload["requesting_agent"] = self.requesting_agent
        if self.task_complexity:
            payload["task_complexity"] = self.task_complexity
        if self.llm_invoked:
            payload["llm_invoked"] = True
        if self.error:
            payload["error"] = self.error
        if self.extra:
            payload.update(self.extra)
        logger.info("context.call %s", json.dumps(payload, default=str))


@contextmanager
def timed_call(method: str, params_summary: str) -> Iterator[CallLog]:
    log = CallLog(method=method, params_summary=params_summary)
    start = time.perf_counter()
    try:
        yield log
    finally:
        log.cost_ms = (time.perf_counter() - start) * 1000.0
        log.emit()
