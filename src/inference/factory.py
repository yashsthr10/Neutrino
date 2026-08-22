"""Create inference providers from config + credentials."""

from __future__ import annotations

from typing import Any

from src.config.schema import InferenceProviderConfig
from src.credentials.models import ResolvedCredentials
from src.inference.errors import InferenceConfigError, UnsupportedCapability
from src.inference.providers.langchain_provider import (
    LangChainProvider,
    openrouter_base_url,
)
from src.inference.providers.openai_compatible import OpenAICompatibleProvider


def create_provider(
    config: InferenceProviderConfig,
    credentials: ResolvedCredentials,
    *,
    langchain_chat_model: Any | None = None,
) -> Any:
    if config.type == "openai-compatible":
        return OpenAICompatibleProvider(config, credentials)
    if config.type == "native":
        vendor = (config.vendor or "").lower()
        if not vendor:
            raise InferenceConfigError("native provider requires vendor")
        # OpenRouter speaks the OpenAI Chat Completions API (incl. SSE streaming).
        # Prefer the httpx streamer over LangChain's buffered invoke→fake-stream path.
        if vendor == "openrouter":
            cfg = config.model_copy(update={"base_url": openrouter_base_url(config.base_url)})
            return OpenAICompatibleProvider(cfg, credentials)
        return LangChainProvider(config, credentials, chat_model=langchain_chat_model)
    raise UnsupportedCapability(f"Unknown provider type: {config.type}")
