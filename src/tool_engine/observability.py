"""Structured per-call logging for the Tool Engine."""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

logger = logging.getLogger("tool_engine")

EventCallback = Callable[[str, dict[str, Any]], None]


@dataclass
class CallLog:
    method: str
    params_summary: str
    state: str | None = None
    cost_ms: float = 0.0
    success: bool | None = None
    result_bytes: int = 0
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def emit(self) -> None:
        payload = {
            "event": (
                "ToolFailed"
                if self.error
                else ("ToolCompleted" if self.success is True else "ToolStarted")
            ),
            "method": self.method,
            "params_summary": self.params_summary,
            "cost_ms": self.cost_ms,
            "success": self.success,
            "result_bytes": self.result_bytes,
            "state": self.state,
        }
        if self.error:
            payload["error"] = self.error
        if self.extra:
            payload.update(self.extra)
        logger.info("tool_engine.call %s", json.dumps(payload, default=str))


@contextmanager
def timed_call(
    method: str,
    params_summary: str,
    *,
    state: str | None = None,
    on_event: EventCallback | None = None,
) -> Iterator[CallLog]:
    log = CallLog(method=method, params_summary=params_summary, state=state)
    if on_event:
        on_event(
            "ToolStarted",
            {"tool": method, "params_summary": params_summary, "state": state},
        )
    start = time.perf_counter()
    try:
        yield log
    finally:
        log.cost_ms = (time.perf_counter() - start) * 1000.0
        log.emit()
        if on_event:
            event = "ToolFailed" if log.error or log.success is False else "ToolCompleted"
            on_event(
                event,
                {
                    "tool": method,
                    "params_summary": params_summary,
                    "state": state,
                    "cost_ms": log.cost_ms,
                    "success": log.success,
                    "result_bytes": log.result_bytes,
                    "error": log.error,
                },
            )
