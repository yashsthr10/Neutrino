"""Provider base protocol."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from src.inference.models.capabilities import ProviderCapabilities
from src.inference.models.request import InferenceRequest
from src.inference.models.response import (
    HealthStatus,
    InferenceResponse,
    InferenceStreamEvent,
    ModelInfo,
)


class InferenceProvider(Protocol):
    name: str

    def connect(self) -> None: ...

    def health(self) -> HealthStatus: ...

    def list_models(self) -> list[ModelInfo]: ...

    def chat(self, request: InferenceRequest) -> InferenceResponse: ...

    def stream(self, request: InferenceRequest) -> Iterator[InferenceStreamEvent]: ...

    def capabilities(self) -> ProviderCapabilities: ...

    def close(self) -> None: ...
