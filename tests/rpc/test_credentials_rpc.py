"""RPC credentials.* methods — never return secret values."""

from __future__ import annotations

from pathlib import Path

from src.credentials import CredentialManager, MemoryStore
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


def test_credentials_list_set_remove(tmp_path: Path) -> None:
    import io

    store = MemoryStore()
    mgr = CredentialManager(store=store)
    out = io.StringIO()
    server = build_server(
        tmp_path,
        NdjsonWriter(out),
        credentials=mgr,
        auto_approve=True,
        auto_recover=True,
    )
    hello = _hello(server)
    assert hello is not None
    caps = hello["result"]["capabilities"]
    assert "credentials.set" in caps

    listed = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "credentials.list",
            "params": {"profile": "default"},
        }
    )
    assert listed is not None
    providers = {p["providerId"]: p for p in listed["result"]["providers"]}
    assert providers["openai"]["configured"] is False

    set_resp = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "credentials.set",
            "params": {
                "providerId": "openai",
                "fields": {"api_key": "sk-secret-value"},
            },
        }
    )
    assert set_resp is not None
    assert set_resp["result"]["ok"] is True
    # Response must not echo the secret
    assert "sk-secret-value" not in str(set_resp)

    listed2 = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "credentials.list",
            "params": {},
        }
    )
    assert listed2 is not None
    providers2 = {p["providerId"]: p for p in listed2["result"]["providers"]}
    assert providers2["openai"]["configured"] is True
    assert "sk-secret-value" not in str(listed2)

    # Stored in manager
    assert mgr.get("openai").fields["api_key"] == "sk-secret-value"

    rm = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "credentials.remove",
            "params": {"providerId": "openai"},
        }
    )
    assert rm is not None
    assert rm["result"]["ok"] is True


def test_credentials_set_unknown_provider(tmp_path: Path) -> None:
    import io

    out = io.StringIO()
    server = build_server(
        tmp_path,
        NdjsonWriter(out),
        credentials=CredentialManager(store=MemoryStore()),
    )
    _hello(server)
    resp = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "credentials.set",
            "params": {"providerId": "nope", "fields": {"api_key": "x"}},
        }
    )
    assert resp is not None
    assert "error" in resp
