"""Structured per-call logging for RNA."""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger("rna")


@dataclass
class CallLog:
    method: str
    params_summary: str
    cost_ms: float = 0.0
    cache_hit: bool = False
    confidence: str | None = None
    degraded: bool = False
    backend_tier: str | None = None
    network_egress: bool = False
    provider: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def emit(self) -> None:
        payload = {
            "method": self.method,
            "params_summary": self.params_summary,
            "cost_ms": self.cost_ms,
            "cache_hit": self.cache_hit,
            "confidence": self.confidence,
            "degraded": self.degraded,
            "backend_tier": self.backend_tier,
            "network_egress": self.network_egress,
        }
        if self.provider:
            payload["provider"] = self.provider
        if self.error:
            payload["error"] = self.error
        if self.extra:
            payload.update(self.extra)
        logger.info("rna.call %s", json.dumps(payload, default=str))


@contextmanager
def timed_call(method: str, params_summary: str) -> Iterator[CallLog]:
    log = CallLog(method=method, params_summary=params_summary)
    start = time.perf_counter()
    try:
        yield log
    finally:
        log.cost_ms = (time.perf_counter() - start) * 1000.0
        log.emit()
