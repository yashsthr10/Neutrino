"""Execute bound handlers with timing and error capture."""

from __future__ import annotations

from typing import Any

from src.tool_engine.dispatcher import Handler
from src.tool_engine.errors import ExecutionError
from src.tool_engine.observability import EventCallback, timed_call


class ToolExecutor:
    def __init__(self, *, on_event: EventCallback | None = None) -> None:
        self._on_event = on_event

    def execute(
        self,
        handler: Handler,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        state: str,
    ) -> tuple[Any, float]:
        summary = _summarize_args(arguments)
        with timed_call(tool_name, summary, state=state, on_event=self._on_event) as log:
            try:
                result = handler(**arguments)
                log.success = True
                return result, log.cost_ms
            except Exception as exc:  # noqa: BLE001
                log.success = False
                log.error = type(exc).__name__
                raise ExecutionError(f"{tool_name} failed: {exc}") from exc


def _summarize_args(arguments: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in list(arguments.items())[:8]:
        text = repr(value)
        if len(text) > 48:
            text = text[:45] + "..."
        parts.append(f"{key}={text}")
    return ", ".join(parts)
