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


def test_stream_token_deltas_and_tool_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        body = json.loads(request.content.decode("utf-8"))
        assert body.get("stream") is True
        chunks = [
            {
                "choices": [
                    {"delta": {"content": "Hi"}, "finish_reason": None},
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "c1",
                                    "function": {"name": "rna.read_file", "arguments": ""},
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"arguments": '{"path":"a.txt"}'},
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ]
            },
            {
                "choices": [{"delta": {}, "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 9},
            },
        ]
        lines = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(
            200,
            content=lines.encode("utf-8"),
            headers={"content-type": "text/event-stream"},
        )

    client = httpx.Client(transport=_transport(handler), base_url="https://openrouter.ai/api/v1")
    provider = OpenAICompatibleProvider(
        InferenceProviderConfig(
            type="native",
            vendor="openrouter",
            model="deepseek/deepseek-v4-flash",
            base_url="https://openrouter.ai/api/v1",
        ),
        ResolvedCredentials(
            provider_id="openrouter",
            profile="default",
            kind="api_key",
            fields={"api_key": "sk-or"},
            source="cli",
        ),
        client=client,
    )
    from src.inference.stream_accumulator import accumulate_stream

    resp = accumulate_stream(
        provider.stream(InferenceRequest(messages=(Message(role="user", content="hi"),)))
    )
    assert resp.content == "Hi"
    assert resp.finish_reason == "tool_calls"
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "rna.read_file"
    assert json.loads(resp.tool_calls[0].arguments)["path"] == "a.txt"
    assert resp.usage.input_tokens == 5
    assert resp.usage.output_tokens == 9
