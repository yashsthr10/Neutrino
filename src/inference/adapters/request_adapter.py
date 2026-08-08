"""Adapt InferenceRequest → OpenAI Chat Completions JSON body."""

from __future__ import annotations

from typing import Any

from src.inference.models.request import InferenceRequest, Message


def messages_to_openai(messages: tuple[Message, ...] | list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        item: dict[str, Any] = {"role": m.role}
        if m.content is not None:
            item["content"] = m.content
        if m.tool_call_id:
            item["tool_call_id"] = m.tool_call_id
        if m.name:
            item["name"] = m.name
        if m.tool_calls:
            item["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in m.tool_calls
            ]
        out.append(item)
    return out


def request_to_openai_body(
    request: InferenceRequest,
    *,
    default_model: str,
    default_temperature: float,
    default_max_tokens: int | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": request.model or default_model,
        "messages": messages_to_openai(request.messages),
        "temperature": (
            request.temperature if request.temperature is not None else default_temperature
        ),
    }
    max_tokens = request.max_tokens if request.max_tokens is not None else default_max_tokens
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    if request.tools:
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters or {"type": "object", "properties": {}},
                },
            }
            for t in request.tools
        ]
    if request.tool_choice is not None:
        body["tool_choice"] = request.tool_choice
    return body
