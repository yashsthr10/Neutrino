"""Collect provider stream events into a final InferenceResponse."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Literal

from src.inference.errors import StreamingError
from src.inference.models.request import ToolCall
from src.inference.models.response import FinishReason, InferenceResponse, InferenceStreamEvent
from src.inference.models.usage import Usage

StreamChannel = Literal["reasoning", "content"]


def stream_events_from_response(
    response: InferenceResponse,
) -> Iterator[InferenceStreamEvent]:
    """Expand a completed response into stream events (for test fakes)."""
    if response.content:
        yield InferenceStreamEvent(type="delta_text", text=response.content)
    for index, tool_call in enumerate(response.tool_calls):
        yield InferenceStreamEvent(
            type="tool_call_delta",
            tool_call=tool_call,
            tool_index=index,
        )
    if response.usage.input_tokens or response.usage.output_tokens:
        yield InferenceStreamEvent(type="usage", usage=response.usage)
    yield InferenceStreamEvent(type="done", finish_reason=response.finish_reason)


def accumulate_stream(
    events: Iterator[InferenceStreamEvent],
    *,
    on_delta: Callable[[StreamChannel, str], None] | None = None,
) -> InferenceResponse:
    """Drain a stream iterator, optionally forwarding text deltas to a callback."""
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_acc: dict[int, dict[str, str]] = {}
    usage = Usage()
    finish_reason: FinishReason = "unknown"
    model: str | None = None

    for event in events:
        if event.type == "delta_text" and event.text:
            content_parts.append(event.text)
            if on_delta:
                on_delta("content", event.text)
        elif event.type == "delta_reasoning" and event.text:
            reasoning_parts.append(event.text)
            if on_delta:
                on_delta("reasoning", event.text)
        elif event.type == "tool_call_delta" and event.tool_call is not None:
            idx = event.tool_index if event.tool_index is not None else len(tool_acc)
            row = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
            tc = event.tool_call
            if tc.id:
                row["id"] = tc.id
            if tc.name:
                row["name"] = tc.name
            if tc.arguments:
                row["arguments"] += tc.arguments
        elif event.type == "usage" and event.usage is not None:
            usage = event.usage
        elif event.type == "done":
            finish_reason = event.finish_reason or "stop"
        elif event.type == "error":
            raise StreamingError(event.error or "stream error")

    tool_calls = tuple(
        ToolCall(id=row["id"], name=row["name"], arguments=row["arguments"] or "{}")
        for _, row in sorted(tool_acc.items())
        if row["name"]
    )
    content = "".join(content_parts) or None
    metadata: dict[str, object] = {}
    if reasoning_parts:
        metadata["reasoning"] = "".join(reasoning_parts)
    if tool_calls and finish_reason == "unknown":
        finish_reason = "tool_calls"

    return InferenceResponse(
        content=content,
        tool_calls=tool_calls,
        usage=usage,
        finish_reason=finish_reason,
        model=model,
        metadata=metadata,
    )
