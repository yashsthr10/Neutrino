"""Credential manager tests."""

from __future__ import annotations

import pytest

from src.credentials import (
    CredentialManager,
    CredentialNotFound,
    CredentialRecord,
    MemoryStore,
)


def test_memory_set_get_delete() -> None:
    store = MemoryStore()
    mgr = CredentialManager(store=store)
    mgr.set(
        "openai",
        CredentialRecord(kind="api_key", fields={"api_key": "sk-test"}),
        profile="work",
    )
    rec = mgr.get("openai", profile="work")
    assert rec.fields["api_key"] == "sk-test"
    mgr.delete("openai", profile="work")
    with pytest.raises(CredentialNotFound):
        mgr.get("openai", profile="work")


def test_env_beats_store(monkeypatch: pytest.MonkeyPatch) -> None:
    store = MemoryStore()
    store.set(
        "default",
        "openai",
        CredentialRecord(kind="api_key", fields={"api_key": "from-store"}),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    mgr = CredentialManager(store=store)
    resolved = mgr.resolve("openai", profile="default")
    assert resolved.source == "env"
    assert resolved.fields["api_key"] == "from-env"


def test_aws_multi_field_round_trip() -> None:
    store = MemoryStore()
    mgr = CredentialManager(store=store)
    mgr.set(
        "bedrock",
        CredentialRecord(
            kind="aws",
            fields={
                "access_key_id": "AKIAxxx",
                "secret_access_key": "secret",
                "session_token": "tok",
            },
        ),
    )
    rec = mgr.get("bedrock")
    assert rec.kind == "aws"
    assert rec.fields["access_key_id"] == "AKIAxxx"


def test_azure_record() -> None:
    store = MemoryStore()
    mgr = CredentialManager(store=store)
    mgr.set("azure_openai", CredentialRecord(kind="azure", fields={"api_key": "az-key"}))
    assert mgr.resolve("azure_openai").fields["api_key"] == "az-key"


def test_openai_compatible_allows_none() -> None:
    mgr = CredentialManager(store=MemoryStore())
    resolved = mgr.resolve("openai-compatible")
    assert resolved.kind == "none"
    assert resolved.source == "none"


def test_bedrock_aws_profile_hint() -> None:
    mgr = CredentialManager(store=MemoryStore())
    resolved = mgr.resolve(
        "bedrock", config_hints={"aws_profile": "dev", "region": "us-east-1"}
    )
    assert resolved.source == "aws_profile"
    assert resolved.hints["aws_profile"] == "dev"


def test_list_status_marks_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    store = MemoryStore()
    mgr = CredentialManager(store=store)
    mgr.set("anthropic", CredentialRecord(kind="api_key", fields={"api_key": "x"}))
    statuses = {s.provider_id: s for s in mgr.list_status()}
    assert statuses["anthropic"].configured is True
    assert statuses["groq"].configured is False


def test_auth_cli_list(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from src.credentials import cli as auth_cli

    store = MemoryStore()
    monkeypatch.setattr(auth_cli, "default_store", lambda: store)
    auth_cli.main(["list"])
    out = capsys.readouterr().out
    assert "openai" in out
