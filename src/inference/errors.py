"""Inference subsystem errors — never expose vendor SDK exceptions to the runtime."""

from __future__ import annotations

import json
from typing import Any


class InferenceError(Exception):
    """Base inference error."""


class InferenceConfigError(InferenceError):
    """Invalid provider configuration."""


class InferenceConnectionError(InferenceError):
    """Provider unreachable or health check failed."""


class AuthenticationError(InferenceError):
    """Invalid or missing credentials."""


class ProviderUnavailable(InferenceError):
    """Provider temporarily unavailable."""


class ModelNotFound(InferenceError):
    """Configured model is not available."""


class StreamingError(InferenceError):
    """Streaming failed mid-response."""


class Timeout(InferenceError):
    """Request timed out."""


class RateLimitExceeded(InferenceError):
    """Provider rate limit hit."""


class UnsupportedCapability(InferenceError):
    """Requested capability or vendor SDK is unavailable."""


class ToolUseFailed(InferenceError):
    """Provider rejected a malformed / incomplete tool call (recoverable).

    Common with Groq when the model emits XML-style ``<tool_call>`` text instead
    of native function calling, or truncates a large tool argument mid-stream.
    """

    def __init__(self, message: str, *, failed_generation: str | None = None) -> None:
        super().__init__(message)
        self.failed_generation = failed_generation


def is_tool_use_failed_message(text: str) -> bool:
    lower = text.lower()
    return "tool_use_failed" in lower or "failed to call a function" in lower


def extract_failed_generation(exc: BaseException | str) -> str | None:
    """Pull ``failed_generation`` out of a Groq/OpenAI-style error payload."""
    fg = getattr(exc, "failed_generation", None)
    if isinstance(fg, str) and fg.strip():
        return fg

    text = str(exc)
    # Prefer key forms so we don't match prose like "See 'failed_generation' for…".
    for key in ("'failed_generation':", '"failed_generation":'):
        idx = text.find(key)
        if idx < 0:
            continue
        rest = text[idx + len(key) :].lstrip()
        if rest.startswith(("'", '"')):
            return _unquote_python_string(rest, rest[0])

    try:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            # Groq often embeds a Python-repr dict; try JSON after quote normalize.
            snippet = text[start : end + 1]
            try:
                payload: Any = json.loads(snippet)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                err = payload.get("error")
                if isinstance(err, dict) and isinstance(err.get("failed_generation"), str):
                    return err["failed_generation"]
    except (TypeError, ValueError):
        pass
    return None


def _unquote_python_string(rest: str, quote: str) -> str | None:
    if not rest or rest[0] != quote:
        return None
    out: list[str] = []
    i = 1
    while i < len(rest):
        ch = rest[i]
        if ch == "\\" and i + 1 < len(rest):
            nxt = rest[i + 1]
            escapes = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"'}
            out.append(escapes.get(nxt, nxt))
            i += 2
            continue
        if ch == quote:
            return "".join(out)
        out.append(ch)
        i += 1
    return "".join(out) if out else None
