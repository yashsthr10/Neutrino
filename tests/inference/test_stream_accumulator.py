"""Stream accumulation and Ollama reasoning delta tests."""

from __future__ import annotations

import json

import httpx

from src.config.schema import InferenceProviderConfig
from src.credentials.models import ResolvedCredentials
from src.inference.models.request import InferenceRequest, Message, ToolCall
from src.inference.models.response import InferenceStreamEvent
from src.inference.providers.openai_compatible import OpenAICompatibleProvider
from src.inference.stream_accumulator import accumulate_stream


def _transport(handler):  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


def test_stream_parses_ollama_reasoning_delta() -> None:
    chunks = [
        'data: {"choices":[{"delta":{"reasoning":"Let me"}}]}\n\n',
        'data: {"choices":[{"delta":{"reasoning":" think"}}]}\n\n',
        'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n',
        "data: [DONE]\n\n",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content="".join(chunks))

    client = httpx.Client(transport=_transport(handler), base_url="http://test/v1", timeout=5.0)
    provider = OpenAICompatibleProvider(
        InferenceProviderConfig(model="qwen3:8b", base_url="http://test/v1"),
        ResolvedCredentials(
            provider_id="ollama",
            profile="default",
            kind="none",
            fields={},
            source="none",
        ),
        client=client,
    )
    events = list(provider.stream(InferenceRequest(messages=(Message(role="user", content="hi"),))))
    provider.close()
    reasoning = [e for e in events if e.type == "delta_reasoning"]
    content = [e for e in events if e.type == "delta_text"]
    assert [e.text for e in reasoning] == ["Let me", " think"]
    assert [e.text for e in content] == ["Hi"]


def test_accumulate_stream_forwards_deltas() -> None:
    seen: list[tuple[str, str]] = []

    def events():  # type: ignore[no-untyped-def]
        yield InferenceStreamEvent(type="delta_reasoning", text="a")
        yield InferenceStreamEvent(type="delta_reasoning", text="b")
        yield InferenceStreamEvent(type="delta_text", text="answer")
        yield InferenceStreamEvent(type="done", finish_reason="stop")

    resp = accumulate_stream(events(), on_delta=lambda ch, txt: seen.append((ch, txt)))
    assert resp.content == "answer"
    assert resp.metadata.get("reasoning") == "ab"
    assert seen == [("reasoning", "a"), ("reasoning", "b"), ("content", "answer")]


def test_accumulate_stream_merges_tool_call_deltas() -> None:
    def events():  # type: ignore[no-untyped-def]
        yield InferenceStreamEvent(
            type="tool_call_delta",
            tool_index=0,
            tool_call=ToolCall(id="c1", name="rna.find", arguments='{"name":'),
        )
        yield InferenceStreamEvent(
            type="tool_call_delta",
            tool_index=0,
            tool_call=ToolCall(id="", name="", arguments='"Foo"}'),
        )
        yield InferenceStreamEvent(type="done", finish_reason="tool_calls")

    resp = accumulate_stream(events())
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "rna.find"
    assert json.loads(resp.tool_calls[0].arguments)["name"] == "Foo"
