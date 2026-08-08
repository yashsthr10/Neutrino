"""Classify inference responses into tool_calls / final / invalid / error."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.inference.models.request import ToolCall
from src.inference.models.response import InferenceResponse


@dataclass(frozen=True, slots=True)
class ClassifiedOutcome:
    kind: Literal["tool_calls", "final", "invalid", "error"]
    tool_calls: tuple[ToolCall, ...] = ()
    content: str | None = None
    message: str | None = None


def classify(response: InferenceResponse | None, *, error: str | None = None) -> ClassifiedOutcome:
    if error:
        return ClassifiedOutcome(kind="error", message=error)
    if response is None:
        return ClassifiedOutcome(kind="error", message="empty_response")
    if response.finish_reason == "error":
        return ClassifiedOutcome(
            kind="error",
            content=response.content,
            message=response.content or "inference_error",
        )
    if response.tool_calls:
        for tc in response.tool_calls:
            if not tc.name or not isinstance(tc.arguments, str):
                return ClassifiedOutcome(
                    kind="invalid",
                    message="malformed_tool_call",
                    content=response.content,
                )
        return ClassifiedOutcome(
            kind="tool_calls",
            tool_calls=response.tool_calls,
            content=response.content,
        )

    content = (response.content or "").strip()
    # Gemini often returns empty / signature-only payloads — do not treat as done.
    if not content or _looks_like_empty_thinking_dump(content):
        return ClassifiedOutcome(
            kind="invalid",
            message="empty_or_non_substantive_response",
            content=response.content,
        )
    # Qwen/Groq sometimes put XML tool markup in content instead of tool_calls.
    if _looks_like_xml_tool_markup(content):
        return ClassifiedOutcome(
            kind="invalid",
            message="xml_tool_markup_in_content",
            content=response.content,
        )

    if response.finish_reason in {"stop", "length", "unknown"} or content:
        return ClassifiedOutcome(kind="final", content=content)
    return ClassifiedOutcome(
        kind="invalid", message="unclassified_response", content=response.content
    )


def _looks_like_empty_thinking_dump(content: str) -> bool:
    """Detect stringified Gemini blocks with empty text + signature extras."""
    if "'type': 'text'" in content or '"type": "text"' in content:
        if "signature" in content and ("'text': ''" in content or '"text": ""' in content):
            # No real user-visible text besides the dump
            return len(content) > 80
    return False


def _looks_like_xml_tool_markup(content: str) -> bool:
    lower = content.lower()
    return "<tool_call>" in lower or "<function=" in lower or "<parameter=" in lower
