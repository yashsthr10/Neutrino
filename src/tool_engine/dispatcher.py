"""Map handler_key → capability callable."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.tool_engine.errors import ToolNotFound

Handler = Callable[..., Any]


class ToolDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def bind(self, handler_key: str, handler: Handler) -> None:
        self._handlers[handler_key] = handler

    def resolve(self, handler_key: str) -> Handler:
        try:
            return self._handlers[handler_key]
        except KeyError as exc:
            raise ToolNotFound(f"No handler bound for {handler_key!r}") from exc
