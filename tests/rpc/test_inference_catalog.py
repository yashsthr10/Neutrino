"""inference.catalog / listModels / runtime.setModel — creds-gated."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from src.config.schema import InferenceProviderConfig
from src.credentials import CredentialManager, CredentialRecord, MemoryStore
from src.rpc.framing import NdjsonWriter
from src.rpc.server import build_server


def _hello(server):  # type: ignore[no-untyped-def]
    return server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "session.hello",
            "params": {"protocolVersion": "1.0.0", "cwd": "/tmp"},
        }
    )


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "NEUTRINO_INFERENCE_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    # user_config_dir = XDG_CONFIG_HOME/neutrino
    (tmp_path / "xdg" / "neutrino").mkdir(parents=True, exist_ok=True)

    store = MemoryStore()
    mgr = CredentialManager(store=store)
    out = io.StringIO()
    srv = build_server(
        tmp_path,
        NdjsonWriter(out),
        credentials=mgr,
        inference=InferenceProviderConfig(
            type="openai-compatible",
            model="llama3.2",
            base_url="http://127.0.0.1:9/v1",  # unreachable — catalog fallback
            timeout_s=1.0,
        ),
    )
    _hello(srv)
    return srv, mgr, out


def test_catalog_only_openai_compatible_without_creds(server) -> None:  # type: ignore[no-untyped-def]
    srv, _mgr, _out = server
    resp = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "inference.catalog",
            "params": {},
        }
    )
    assert resp is not None
    providers = {p["providerId"] for p in resp["result"]["providers"]}
    assert providers == {"openai-compatible", "ollama"}
    assert resp["result"]["active"]["providerId"] == "ollama"
    assert resp["result"]["active"]["model"] == "llama3.2"


def test_catalog_includes_provider_after_cred(server) -> None:  # type: ignore[no-untyped-def]
    srv, mgr, _out = server
    mgr.set("openai", CredentialRecord(kind="api_key", fields={"api_key": "sk-test"}))
    resp = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "inference.catalog",
            "params": {},
        }
    )
    assert resp is not None
    providers = {p["providerId"] for p in resp["result"]["providers"]}
    assert "openai" in providers
    assert "openai-compatible" in providers
    assert "anthropic" not in providers


def test_list_models_blocked_without_cred(server) -> None:  # type: ignore[no-untyped-def]
    srv, _mgr, _out = server
    resp = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "inference.listModels",
            "params": {"providerId": "anthropic"},
        }
    )
    assert resp is not None
    assert "error" in resp
    assert (
        "credentials" in resp["error"]["message"].lower()
        or "auth" in resp["error"]["message"].lower()
    )


def test_set_model_openai_compatible(server, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    srv, _mgr, out = server
    resp = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "runtime.setModel",
            "params": {"providerId": "openai-compatible", "model": "qwen2.5-coder"},
        }
    )
    assert resp is not None
    assert resp["result"]["ok"] is True
    assert resp["result"]["model"] == "qwen2.5-coder"
    events = [line for line in out.getvalue().splitlines() if "model.changed" in line]
    assert events
    persisted = tmp_path / "xdg" / "neutrino" / "config.toml"
    assert persisted.is_file()
    text = persisted.read_text(encoding="utf-8")
    assert 'model = "qwen2.5-coder"' in text
    assert 'type = "openai-compatible"' in text


def test_set_model_native_requires_cred(server) -> None:  # type: ignore[no-untyped-def]
    srv, mgr, _out = server
    blocked = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "runtime.setModel",
            "params": {"providerId": "openai", "model": "gpt-4o"},
        }
    )
    assert blocked is not None
    assert "error" in blocked

    mgr.set("openai", CredentialRecord(kind="api_key", fields={"api_key": "sk-test"}))
    ok = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "runtime.setModel",
            "params": {"providerId": "openai", "model": "gpt-4o"},
        }
    )
    assert ok is not None
    assert ok["result"]["ok"] is True
    assert ok["result"]["providerId"] == "openai"


def test_set_model_openrouter_does_not_inherit_ollama_base_url(server) -> None:  # type: ignore[no-untyped-def]
    """Switching from local openai-compatible must not keep :11434 as OpenRouter host."""
    from src.rpc.inference_rpc import OPENROUTER_DEFAULT_BASE_URL, config_for_provider

    active = InferenceProviderConfig(
        type="openai-compatible",
        model="llama3.2",
        base_url="http://127.0.0.1:11434/v1",
    )
    cfg = config_for_provider(
        "openrouter",
        model="deepseek/deepseek-v4-flash-0731",
        active=active,
    )
    assert cfg.vendor == "openrouter"
    assert cfg.model == "deepseek/deepseek-v4-flash-0731"
    assert cfg.base_url == OPENROUTER_DEFAULT_BASE_URL

    srv, mgr, _out = server
    mgr.set("openrouter", CredentialRecord(kind="api_key", fields={"api_key": "sk-or"}))
    ok = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "runtime.setModel",
            "params": {
                "providerId": "openrouter",
                "model": "deepseek/deepseek-v4-flash-0731",
            },
        }
    )
    assert ok is not None
    assert ok["result"]["ok"] is True
    assert ok["result"]["providerId"] == "openrouter"
    assert ok["result"]["baseUrl"] == OPENROUTER_DEFAULT_BASE_URL


def test_set_model_ollama(server, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    srv, mgr, _out = server
    mgr.set(
        "ollama",
        CredentialRecord(kind="none", fields={"base_url": "http://127.0.0.1:11434"}),
    )
    resp = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "runtime.setModel",
            "params": {"providerId": "ollama", "model": "llama3.2"},
        }
    )
    assert resp is not None
    assert resp["result"]["ok"] is True
    assert resp["result"]["providerId"] == "ollama"
    assert resp["result"]["baseUrl"] == "http://127.0.0.1:11434/v1"
    persisted = tmp_path / "xdg" / "neutrino" / "config.toml"
    assert persisted.is_file()
    assert 'model = "llama3.2"' in persisted.read_text(encoding="utf-8")


def test_list_models_returns_catalog_for_eligible(server) -> None:  # type: ignore[no-untyped-def]
    srv, mgr, _out = server
    mgr.set("groq", CredentialRecord(kind="api_key", fields={"api_key": "g"}))
    resp = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "inference.listModels",
            "params": {"providerId": "groq"},
        }
    )
    assert resp is not None
    ids = {m["id"] for m in resp["result"]["models"]}
    assert "qwen/qwen3.6-27b" in ids
    assert "llama-3.3-70b-versatile" in ids
