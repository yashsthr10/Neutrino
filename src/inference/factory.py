"""Create inference providers from config + credentials."""

from __future__ import annotations

from typing import Any

from src.config.schema import InferenceProviderConfig
from src.credentials.models import ResolvedCredentials
from src.inference.errors import InferenceConfigError, UnsupportedCapability
from src.inference.providers.langchain_provider import LangChainProvider
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
        return LangChainProvider(config, credentials, chat_model=langchain_chat_model)
    raise UnsupportedCapability(f"Unknown provider type: {config.type}")
