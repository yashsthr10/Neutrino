"""Conversation Manager contract and session isolation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.context import ConversationManager, ConversationManagerPort
from src.context.config import ContextConfig
from src.context.errors import ContextSecurityError
from src.context.runtime.conversation_context import Message


def test_satisfies_port(conversation_manager: ConversationManager) -> None:
    assert isinstance(conversation_manager, ConversationManagerPort)


def test_append_and_get_recent(conversation_manager: ConversationManager) -> None:
    conversation_manager.append(
        Message(role="user", content="hello world", created_at="2026-01-01T00:00:00Z")
    )
    conversation_manager.append(
        Message(
            role="assistant",
            content="we'll use Redis for caching",
            created_at="2026-01-01T00:00:01Z",
        )
    )
    recent = conversation_manager.get_recent(n=10)
    assert len(recent.data) == 2
    decisions = conversation_manager.get_decisions()
    assert any("Redis" in d.statement for d in decisions.data)


def test_summarize_without_chat_model(conversation_manager: ConversationManager) -> None:
    conversation_manager.append(
        Message(role="user", content="task one", created_at="2026-01-01T00:00:00Z")
    )
    result = conversation_manager.summarize(force=True)
    assert result.meta.degraded is True
    assert result.meta.reason == "no_chat_model_configured"
    assert result.data.text


def test_summarize_chat_model_raises(tmp_path: Path) -> None:
    class Boom:
        def complete(self, messages: list[dict[str, str]]) -> str:
            raise RuntimeError("down")

    cfg = ContextConfig(cache_dir=tmp_path / "c")
    cm = ConversationManager(
        session_id="s", config=cfg, chat_model=Boom(), cache_dir=cfg.resolved_cache_dir()
    )
    cm.append(Message(role="user", content="hi", created_at="t"))
    result = cm.summarize(force=True)
    assert result.meta.degraded is True
    assert result.meta.reason == "summarizer_unavailable"


def test_session_isolation(tmp_path: Path) -> None:
    cfg = ContextConfig(cache_dir=tmp_path / "c")
    a = ConversationManager(session_id="a", config=cfg, cache_dir=cfg.resolved_cache_dir())
    b = ConversationManager(session_id="b", config=cfg, cache_dir=cfg.resolved_cache_dir())
    a.append(Message(role="user", content="only in a", created_at="t1"))
    b.append(Message(role="user", content="only in b", created_at="t2"))
    assert all("only in a" in m.content for m in a.get_recent().data)
    assert all("only in b" in m.content for m in b.get_recent().data)
    assert not any("only in b" in m.content for m in a.get_recent().data)


def test_forced_session_mismatch_raises(tmp_path: Path) -> None:
    cfg = ContextConfig(cache_dir=tmp_path / "c")
    cm = ConversationManager(session_id="good", config=cfg, cache_dir=cfg.resolved_cache_dir())
    cm.append(Message(role="user", content="x", created_at="t", id="msg-1"))
    db = tmp_path / "c" / "conversation" / "good" / "messages.sqlite"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("UPDATE messages SET session_id=? WHERE id=?", ("evil", "msg-1"))
        conn.commit()
    with pytest.raises(ContextSecurityError):
        cm._store.get_by_id("msg-1")


def test_clear_keeps_decisions(conversation_manager: ConversationManager) -> None:
    conversation_manager.append(
        Message(
            role="assistant",
            content="decided to use SQLite",
            created_at="t",
        )
    )
    assert conversation_manager.get_decisions().data
    conversation_manager.clear(keep_decisions=True)
    assert conversation_manager.get_recent().data == []
    assert conversation_manager.get_decisions().data
    conversation_manager.clear(keep_decisions=False)
    assert conversation_manager.get_decisions().data == []
