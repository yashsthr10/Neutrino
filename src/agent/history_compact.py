"""Compact older tool results in message history (microcompact)."""

from __future__ import annotations

import json

from src.config.constants import MICROCOMPACT_KEEP_RECENT
from src.inference.models.request import Message

_PROTECTED_TOOLS = frozenset({"rna.read_file", "executor.apply", "context.resolve"})


def compact_tool_history(
    messages: list[Message],
    *,
    keep_recent: int = MICROCOMPACT_KEEP_RECENT,
) -> list[Message]:
    """Replace older tool message bodies with one-line summaries."""
    if keep_recent <= 0 or not messages:
        return messages

    tool_indices = [i for i, m in enumerate(messages) if m.role == "tool"]
    if len(tool_indices) <= keep_recent:
        return messages

    compact_until = tool_indices[-keep_recent]
    out: list[Message] = []
    for i, msg in enumerate(messages):
        if msg.role != "tool" or i >= compact_until:
            out.append(msg)
            continue
        name = msg.name or "tool"
        if name in _PROTECTED_TOOLS and i >= tool_indices[-2] if len(tool_indices) >= 2 else False:
            out.append(msg)
            continue
        summary = _summarize_tool_result(name, msg.content)
        out.append(
            Message(
                role="tool",
                tool_call_id=msg.tool_call_id,
                name=name,
                content=summary,
            )
        )
    return out


def _summarize_tool_result(name: str, content: str | None) -> str:
    try:
        data = json.loads(content or "{}")
    except json.JSONDecodeError:
        return f'{{"success": false, "note": "compact summary for {name}"}}'
    success = data.get("success")
    note = f"[compact] {name} success={success}"
    if isinstance(data.get("data"), dict):
        keys = list(data["data"].keys())[:6]
        if keys:
            note += f" keys={keys}"
    return json.dumps({"success": success, "data": {"summary": note}, "meta": data.get("meta", {})})
