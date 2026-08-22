"""InferenceManager + Context ChatModelPort adapter."""

from __future__ import annotations

from src.config.schema import InferenceProviderConfig
from src.credentials import CredentialManager, MemoryStore
from src.inference import (
    InferenceChatModelAdapter,
    InferenceRequest,
    Message,
    build_inference,
)
from tests.doubles import FakeInferenceProvider


def test_build_inference_with_fake() -> None:
    fake = FakeInferenceProvider(response_text="pong")
    mgr = build_inference(
        InferenceProviderConfig(model="fake-model"),
        CredentialManager(store=MemoryStore()),
        provider=fake,
        start=True,
    )
    assert mgr.health().ok
    resp = mgr.chat(InferenceRequest(messages=(Message(role="user", content="ping"),)))
    assert resp.content == "pong"
    assert fake.connected is True
    mgr.close()


def test_compat_adapter_for_context() -> None:
    fake = FakeInferenceProvider(response_text="summary text")
    mgr = build_inference(
        InferenceProviderConfig(),
        CredentialManager(store=MemoryStore()),
        provider=fake,
    )
    adapter = InferenceChatModelAdapter(mgr)
    out = adapter.complete([{"role": "user", "content": "summarize this"}])
    assert out == "summary text"
    assert len(fake.chat_calls) == 1


def test_langchain_unsupported_vendor() -> None:
    import pytest

    from src.credentials.models import ResolvedCredentials
    from src.inference.errors import UnsupportedCapability
    from src.inference.providers.langchain_provider import LangChainProvider

    bad = LangChainProvider(
        InferenceProviderConfig(type="native", vendor="not-a-vendor", model="x", base_url=None),
        ResolvedCredentials(
            provider_id="openai",
            profile="default",
            kind="none",
            fields={},
            source="none",
        ),
    )
    with pytest.raises(UnsupportedCapability):
        bad.connect()


def test_factory_routes_openrouter_to_openai_compatible_streamer() -> None:
    from src.credentials.models import ResolvedCredentials
    from src.inference.factory import create_provider
    from src.inference.providers.openai_compatible import OpenAICompatibleProvider

    provider = create_provider(
        InferenceProviderConfig(
            type="native",
            vendor="openrouter",
            model="deepseek/deepseek-v4-flash",
            base_url="http://127.0.0.1:11434/v1",
        ),
        ResolvedCredentials(
            provider_id="openrouter",
            profile="default",
            kind="api_key",
            fields={"api_key": "sk-or"},
            source="cli",
        ),
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider._base_url == "https://openrouter.ai/api/v1"
