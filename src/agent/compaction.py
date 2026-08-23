"""Deterministic session history compaction summaries."""

from __future__ import annotations

from src.inference.models.request import Message


def build_session_summary(dropped: list[Message]) -> str:
    """Summarize pruned turns without an LLM call."""
    tools: list[str] = []
    users: list[str] = []
    for msg in dropped:
        if msg.role == "tool" and msg.name:
            tools.append(msg.name)
        elif msg.role == "user" and msg.content and not msg.content.startswith("<system-reminder"):
            text = msg.content.strip().replace("\n", " ")[:120]
            if text and text not in users:
                users.append(text)
    tool_counts: dict[str, int] = {}
    for t in tools:
        tool_counts[t] = tool_counts.get(t, 0) + 1
    tool_line = ", ".join(f"{k}x{v}" for k, v in sorted(tool_counts.items())[:12]) or "(none)"
    user_line = users[-1] if users else "(none)"
    return (
        "[Earlier conversation pruned for context limits.]\n"
        f"Prior user focus: {user_line}\n"
        f"Tools used earlier: {tool_line}"
    )
