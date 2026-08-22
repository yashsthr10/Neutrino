"""LangChain provider stream must preserve tool_calls for the agent loop."""

from __future__ import annotations

from src.config.schema import InferenceProviderConfig
from src.credentials.models import ResolvedCredentials
from src.inference.models.request import InferenceRequest, Message, ToolCall, ToolSpec
from src.inference.models.response import InferenceResponse
from src.inference.models.usage import Usage
from src.inference.providers.langchain_provider import LangChainProvider
from src.inference.stream_accumulator import accumulate_stream


def test_langchain_stream_preserves_tool_calls(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    provider = LangChainProvider(
        InferenceProviderConfig(type="native", vendor="openrouter", model="test"),
        ResolvedCredentials(
            provider_id="openrouter",
            profile="default",
            kind="api_key",
            fields={"api_key": "x"},
            source="cli",
        ),
    )

    expected = InferenceResponse(
        content="calling tools",
        tool_calls=(ToolCall(id="1", name="rna.read_file", arguments='{"path":"info.txt"}'),),
        usage=Usage(input_tokens=10, output_tokens=5),
        finish_reason="tool_calls",
        model="test",
    )
    monkeypatch.setattr(provider, "chat", lambda _request: expected)

    accumulated = accumulate_stream(
        provider.stream(
            InferenceRequest(
                messages=(Message(role="user", content="hi"),),
                tools=(ToolSpec(name="rna.read_file", description="read", parameters={}),),
                tool_choice="auto",
            )
        )
    )
    assert accumulated.finish_reason == "tool_calls"
    assert len(accumulated.tool_calls) == 1
    assert accumulated.tool_calls[0].name == "rna.read_file"
    assert "info.txt" in accumulated.tool_calls[0].arguments
    assert accumulated.content == "calling tools"
