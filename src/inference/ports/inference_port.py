"""Inference Port — stable contract for the runtime."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from src.inference.models.request import InferenceRequest
from src.inference.models.response import (
    HealthStatus,
    InferenceResponse,
    InferenceStreamEvent,
    ModelInfo,
)


@runtime_checkable
class InferencePort(Protocol):
    def health(self) -> HealthStatus: ...

    def list_models(self) -> list[ModelInfo]: ...

    def chat(self, request: InferenceRequest) -> InferenceResponse: ...

    def stream(self, request: InferenceRequest) -> Iterator[InferenceStreamEvent]: ...

    def supports_tools(self) -> bool: ...

    def supports_structured_output(self) -> bool: ...

    def close(self) -> None: ...
