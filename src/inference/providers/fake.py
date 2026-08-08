"""Scripted inference provider for tests."""

from __future__ import annotations

from collections.abc import Iterator

from src.inference.models.capabilities import ProviderCapabilities
from src.inference.models.request import InferenceRequest, ToolCall
from src.inference.models.response import (
    HealthStatus,
    InferenceResponse,
    InferenceStreamEvent,
    ModelInfo,
)
from src.inference.models.usage import Usage


class FakeInferenceProvider:
    name = "fake"

    def __init__(
        self,
        *,
        response_text: str = "OK",
        tool_calls: tuple[ToolCall, ...] = (),
        models: tuple[str, ...] = ("fake-model",),
        healthy: bool = True,
    ) -> None:
        self.response_text = response_text
        self.tool_calls = tool_calls
        self._models = models
        self._healthy = healthy
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
        return InferenceResponse(
            content=self.response_text,
            tool_calls=self.tool_calls,
            usage=Usage(input_tokens=10, output_tokens=5),
            finish_reason="tool_calls" if self.tool_calls else "stop",
            model=self._models[0] if self._models else "fake-model",
        )

    def stream(self, request: InferenceRequest) -> Iterator[InferenceStreamEvent]:
        self.chat_calls.append(request)
        for ch in self.response_text:
            yield InferenceStreamEvent(type="delta_text", text=ch)
        yield InferenceStreamEvent(
            type="usage", usage=Usage(input_tokens=10, output_tokens=len(self.response_text))
        )
        yield InferenceStreamEvent(type="done", finish_reason="stop")
