"""Structured logging for inference calls."""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger("inference")


@dataclass
class CallLog:
    method: str
    provider: str
    model: str | None = None
    cost_ms: float = 0.0
    success: bool | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def emit(self) -> None:
        event = "InferenceFailed" if self.error else (
            "InferenceCompleted" if self.success else "InferenceStarted"
        )
        payload = {
            "event": event,
            "method": self.method,
            "provider": self.provider,
            "model": self.model,
            "cost_ms": self.cost_ms,
            "success": self.success,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }
        if self.error:
            payload["error"] = self.error
        if self.extra:
            payload.update(self.extra)
        logger.info("inference.call %s", json.dumps(payload, default=str))


@contextmanager
def timed_call(method: str, provider: str, *, model: str | None = None) -> Iterator[CallLog]:
    log = CallLog(method=method, provider=provider, model=model)
    start = time.perf_counter()
    try:
        yield log
    finally:
        log.cost_ms = (time.perf_counter() - start) * 1000.0
        log.emit()
