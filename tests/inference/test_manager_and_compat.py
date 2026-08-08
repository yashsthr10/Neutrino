"""InferenceManager + Context ChatModelPort adapter."""

from __future__ import annotations

from src.config.schema import InferenceProviderConfig
from src.credentials import CredentialManager, MemoryStore
from src.inference import (
    FakeInferenceProvider,
    InferenceChatModelAdapter,
    InferenceRequest,
    Message,
    build_inference,
)


def test_build_inference_with_fake() -> None:
    fake = FakeInferenceProvider(response_text="pong")
    mgr = build_inference(
        InferenceProviderConfig(model="fake-model"),
        CredentialManager(store=MemoryStore()),
        fake=fake,
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
        fake=fake,
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
