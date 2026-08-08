"""Inference Manager — lifecycle, routing, retries, observability."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from src.config.schema import InferenceProviderConfig, NeutrinoSettings
from src.credentials import CredentialManager, build_credential_manager
from src.inference.errors import (
    InferenceConnectionError,
    ProviderUnavailable,
    RateLimitExceeded,
    Timeout,
    ToolUseFailed,
)
from src.inference.factory import create_provider
from src.inference.health import ensure_healthy
from src.inference.models.request import InferenceRequest
from src.inference.models.response import (
    HealthStatus,
    InferenceResponse,
    InferenceStreamEvent,
    ModelInfo,
)
from src.inference.observability import timed_call
from src.inference.providers.fake import FakeInferenceProvider


class InferenceManager:
    """Public runtime entrypoint implementing InferencePort."""

    def __init__(
        self,
        config: InferenceProviderConfig,
        credentials: CredentialManager,
        *,
        provider: Any | None = None,
        max_retries: int = 2,
    ) -> None:
        self._config = config
        self._credentials = credentials
        self._provider = provider
        self._max_retries = max_retries
        self._ready = False

    @property
    def config(self) -> InferenceProviderConfig:
        return self._config

    def start(self) -> HealthStatus:
        provider = self._ensure_provider()
        provider.connect()
        status = ensure_healthy(provider)
        self._ready = True
        return status

    def health(self) -> HealthStatus:
        return self._ensure_provider().health()

    def list_models(self) -> list[ModelInfo]:
        return self._ensure_provider().list_models()

    def supports_tools(self) -> bool:
        return self._ensure_provider().capabilities().tools

    def supports_structured_output(self) -> bool:
        return self._ensure_provider().capabilities().structured_output

    def chat(self, request: InferenceRequest) -> InferenceResponse:
        provider = self._ensure_provider()
        with timed_call("chat", provider.name, model=request.model or self._config.model) as log:
            try:
                resp = self._with_retries(lambda: provider.chat(request))
                log.success = True
                log.input_tokens = resp.usage.input_tokens
                log.output_tokens = resp.usage.output_tokens
                return resp
            except Exception as exc:  # noqa: BLE001
                log.success = False
                log.error = type(exc).__name__
                raise

    def stream(self, request: InferenceRequest) -> Iterator[InferenceStreamEvent]:
        provider = self._ensure_provider()
        with timed_call("stream", provider.name, model=request.model or self._config.model) as log:
            try:
                yield from provider.stream(request)
                log.success = True
            except Exception as exc:  # noqa: BLE001
                log.success = False
                log.error = type(exc).__name__
                raise

    def close(self) -> None:
        if self._provider is not None:
            self._provider.close()
            self._ready = False

    def _ensure_provider(self) -> Any:
        if self._provider is None:
            resolved = self._credentials.resolve(
                self._config.provider_id(),
                profile=self._config.credential,
                config_hints=self._config.config_hints(),
            )
            self._provider = create_provider(self._config, resolved)
        return self._provider

    def _with_retries(self, fn):  # type: ignore[no-untyped-def]
        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return fn()
            except ToolUseFailed:
                # Malformed tool markup — retrying the same prompt usually repeats the failure.
                raise
            except (RateLimitExceeded, ProviderUnavailable, Timeout, InferenceConnectionError) as exc:
                last = exc
                if attempt >= self._max_retries:
                    break
                time.sleep(0.05 * (2**attempt))
        assert last is not None
        raise last


def build_inference(
    settings: NeutrinoSettings | InferenceProviderConfig,
    credentials: CredentialManager | None = None,
    *,
    fake: FakeInferenceProvider | None = None,
    langchain_chat_model: Any | None = None,
    start: bool = False,
) -> InferenceManager:
    if isinstance(settings, NeutrinoSettings):
        config = settings.resolved_inference()
    else:
        config = settings
    creds = credentials or build_credential_manager()
    if fake is not None or langchain_chat_model is not None:
        from src.credentials.models import ResolvedCredentials

        resolved = ResolvedCredentials(
            provider_id=config.provider_id(),
            profile=config.credential,
            kind="none",
            fields={},
            source="none",
            hints=config.config_hints(),
        )
        provider = create_provider(
            config,
            resolved,
            fake=fake,
            langchain_chat_model=langchain_chat_model,
        )
        mgr = InferenceManager(config, creds, provider=provider)
    else:
        mgr = InferenceManager(config, creds)
    if start:
        mgr.start()
    return mgr
