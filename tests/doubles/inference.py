"""Scripted inference providers for unit tests."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from src.inference.models.capabilities import ProviderCapabilities
from src.inference.models.request import InferenceRequest, ToolCall
from src.inference.models.response import (
    HealthStatus,
    InferenceResponse,
    InferenceStreamEvent,
    ModelInfo,
)
from src.inference.models.usage import Usage
from src.inference.stream_accumulator import stream_events_from_response


class FakeInferenceProvider:
    name = "fake"

    def __init__(
        self,
        *,
        response_text: str = "OK",
        tool_calls: tuple[ToolCall, ...] = (),
        models: tuple[str, ...] = ("fake-model",),
        healthy: bool = True,
        responses: list[InferenceResponse] | None = None,
    ) -> None:
        self.response_text = response_text
        self.tool_calls = tool_calls
        self._models = models
        self._healthy = healthy
        self._responses = list(responses) if responses is not None else None
        self.chat_calls: list[InferenceRequest] = []
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tools=True, structured_output=True, streaming=True)

    def health(self) -> HealthStatus:
        return HealthStatus(ok=self._healthy, message="fake", models=self._models)

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id=m) for m in self._models]

    def chat(self, request: InferenceRequest) -> InferenceResponse:
        self.chat_calls.append(request)
        if self._responses is not None:
            if not self._responses:
                return InferenceResponse(
                    content="fallback final",
                    usage=Usage(),
                    finish_reason="stop",
                )
            return self._responses.pop(0)
        return InferenceResponse(
            content=self.response_text,
            tool_calls=self.tool_calls,
            usage=Usage(input_tokens=10, output_tokens=5),
            finish_reason="tool_calls" if self.tool_calls else "stop",
            model=self._models[0] if self._models else "fake-model",
        )

    def stream(self, request: InferenceRequest) -> Iterator[InferenceStreamEvent]:
        yield from stream_events_from_response(self.chat(request))

    def supports_tools(self) -> bool:
        return True

    def supports_structured_output(self) -> bool:
        return True


class ScriptedInference(FakeInferenceProvider):
    """Queue of InferenceResponse objects (alias for tests that pass a response list)."""

    def __init__(self, responses: list[InferenceResponse]) -> None:
        super().__init__(responses=responses)


class QueueInference(ScriptedInference):
    """Like ScriptedInference but the queue may contain exceptions to raise."""

    def __init__(self, items: list[InferenceResponse | Exception]) -> None:
        super().__init__([])
        self._items: list[InferenceResponse | Exception] = list(items)

    def chat(self, request: InferenceRequest) -> InferenceResponse:
        self.chat_calls.append(request)
        if not self._items:
            return InferenceResponse(content="fallback", usage=Usage(), finish_reason="stop")
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
