"""Inference / profile config tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config.schema import InferenceProviderConfig, ModelConfig, NeutrinoSettings, ProfileConfig


def test_legacy_ollama_alias() -> None:
    legacy = ModelConfig(provider="ollama", name="qwen3", ollama_base_url="http://localhost:11434")
    inf = legacy.to_inference()
    assert inf.type == "openai-compatible"
    assert inf.base_url == "http://localhost:11434/v1"
    assert inf.model == "qwen3"


def test_settings_legacy_model_field() -> None:
    s = NeutrinoSettings(model=ModelConfig(provider="ollama", name="llama3.2"))
    assert s.inference.type == "openai-compatible"
    assert "11434" in (s.inference.base_url or "")


def test_azure_requires_fields() -> None:
    with pytest.raises(ValidationError):
        InferenceProviderConfig(type="native", vendor="azure_openai", model="gpt-4o")


def test_azure_ok() -> None:
    cfg = InferenceProviderConfig(
        type="native",
        vendor="azure_openai",
        model="gpt-4o",
        azure_endpoint="https://example.openai.azure.com",
        api_version="2024-02-15-preview",
        deployment="gpt-4o",
    )
    assert cfg.provider_id() == "azure_openai"


def test_bedrock_requires_region() -> None:
    with pytest.raises(ValidationError):
        InferenceProviderConfig(type="native", vendor="bedrock", model="anthropic.claude")


def test_profile_resolution() -> None:
    s = NeutrinoSettings(
        inference=InferenceProviderConfig(model="default-model"),
        active_profile="work",
        profiles={
            "work": ProfileConfig(
                name="work",
                inference=InferenceProviderConfig(
                    type="native",
                    vendor="anthropic",
                    model="claude-sonnet-4",
                    base_url=None,
                ),
            )
        },
    )
    assert s.resolved_inference().model == "claude-sonnet-4"
    assert s.resolved_inference().vendor == "anthropic"
