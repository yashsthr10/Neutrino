"""OpenAI-compatible provider tests with httpx mock transport."""

from __future__ import annotations

import json

import httpx

from src.config.schema import InferenceProviderConfig
from src.credentials.models import ResolvedCredentials
from src.inference.models.request import InferenceRequest, Message
from src.inference.providers.openai_compatible import OpenAICompatibleProvider


def _transport(handler):  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


def test_chat_and_health() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "llama3.2"}]})
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                json={
                    "id": "1",
                    "model": "llama3.2",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "hello"},
                        }
                    ],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=_transport(handler), base_url="http://test/v1", timeout=5.0)
    cfg = InferenceProviderConfig(model="llama3.2", base_url="http://test/v1")
    creds = ResolvedCredentials(
        provider_id="openai-compatible",
        profile="default",
        kind="none",
        fields={},
        source="none",
    )
    provider = OpenAICompatibleProvider(cfg, creds, client=client)
    health = provider.health()
    assert health.ok
    assert "llama3.2" in health.models
    resp = provider.chat(InferenceRequest(messages=(Message(role="user", content="hi"),)))
    assert resp.content == "hello"
    assert resp.usage.input_tokens == 3
    provider.close()


def test_tool_calls_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {
                                        "name": "rna.find_symbol",
                                        "arguments": '{"name":"Foo"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {},
            },
        )

    client = httpx.Client(transport=_transport(handler), base_url="http://test/v1")
    provider = OpenAICompatibleProvider(
        InferenceProviderConfig(base_url="http://test/v1"),
        ResolvedCredentials(
            provider_id="openai-compatible",
            profile="default",
            kind="none",
            fields={},
            source="none",
        ),
        client=client,
    )
    resp = provider.chat(InferenceRequest(messages=(Message(role="user", content="x"),)))
    assert resp.tool_calls[0].name == "rna.find_symbol"
    assert json.loads(resp.tool_calls[0].arguments)["name"] == "Foo"
