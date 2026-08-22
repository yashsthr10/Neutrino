"""Session history dual-cap pruning (messages + tokens)."""

from __future__ import annotations

from src.config.constants import (
    SESSION_HISTORY_MAX_MESSAGES,
    SESSION_HISTORY_MAX_TOKENS,
)
from src.inference.models.request import Message, ToolCall
from src.orchestrator.agent_orchestrator import (
    _estimate_message_tokens,
    _history_token_count,
    _trim_session_history,
)


def test_trim_by_message_count() -> None:
    msgs = [Message(role="user", content=f"m{i}") for i in range(20)]
    trimmed = _trim_session_history(
        msgs,
        max_messages=SESSION_HISTORY_MAX_MESSAGES,
        max_tokens=100_000,
    )
    assert len(trimmed) <= SESSION_HISTORY_MAX_MESSAGES
    # Newest kept
    assert trimmed[-1].content == "m19"
    assert any("pruned" in (m.content or "") for m in trimmed if m.role == "user")


def test_trim_by_token_budget() -> None:
    big = "x" * 8_000  # ~2000 tokens each
    msgs = [
        Message(role="user", content=big),
        Message(role="assistant", content=big),
        Message(role="user", content=big),
        Message(role="assistant", content=big),
        Message(role="user", content="please continue"),
    ]
    trimmed = _trim_session_history(msgs, max_messages=12, max_tokens=3_000)
    assert len(trimmed) < len(msgs)
    assert trimmed[-1].content == "please continue"
    assert _history_token_count(trimmed) <= 3_000


def test_trim_drops_leading_orphan_tool_messages() -> None:
    big = "y" * 4_000
    msgs = [
        Message(role="user", content="old task"),
        Message(
            role="assistant",
            content=None,
            tool_calls=(ToolCall(id="1", name="rna.read_file", arguments='{"path":"a"}'),),
        ),
        Message(role="tool", content=big, tool_call_id="1", name="rna.read_file"),
        Message(role="user", content="please continue"),
    ]
    trimmed = _trim_session_history(msgs, max_messages=12, max_tokens=500)
    assert all(m.role != "tool" for m in trimmed)
    assert trimmed[-1].content == "please continue"


def test_estimate_includes_tool_call_arguments() -> None:
    msg = Message(
        role="assistant",
        content=None,
        tool_calls=(
            ToolCall(
                id="1",
                name="executor.apply",
                arguments='{"patch":"' + ("a" * 400) + '"}',
            ),
        ),
    )
    assert _estimate_message_tokens(msg) > 50


def test_defaults_match_documented_caps() -> None:
    assert SESSION_HISTORY_MAX_MESSAGES == 15
    assert SESSION_HISTORY_MAX_TOKENS == 128_000
