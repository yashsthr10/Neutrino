"""Normalize provider JSON → InferenceResponse."""

from __future__ import annotations

from typing import Any

from src.inference.models.request import ToolCall
from src.inference.models.response import FinishReason, InferenceResponse
from src.inference.models.usage import Usage


def parse_openai_chat_completion(payload: dict[str, Any]) -> InferenceResponse:
    choices = payload.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    content = message.get("content")
    tool_calls_raw = message.get("tool_calls") or []
    tool_calls = tuple(
        ToolCall(
            id=str(tc.get("id") or ""),
            name=str((tc.get("function") or {}).get("name") or ""),
            arguments=str((tc.get("function") or {}).get("arguments") or "{}"),
        )
        for tc in tool_calls_raw
    )
    usage_raw = payload.get("usage") or {}
    usage = Usage(
        input_tokens=int(usage_raw.get("prompt_tokens") or usage_raw.get("input_tokens") or 0),
        output_tokens=int(
            usage_raw.get("completion_tokens") or usage_raw.get("output_tokens") or 0
        ),
    )
    finish = str(choice.get("finish_reason") or "unknown")
    finish_reason: FinishReason
    if finish in {"stop", "tool_calls", "length", "content_filter", "error"}:
        finish_reason = finish  # type: ignore[assignment]
    else:
        finish_reason = "unknown"
    return InferenceResponse(
        content=(
            content if isinstance(content, str) else (None if content is None else str(content))
        ),
        tool_calls=tool_calls,
        usage=usage,
        finish_reason=finish_reason,
        model=payload.get("model"),
        metadata={"raw_id": payload.get("id")},
    )
