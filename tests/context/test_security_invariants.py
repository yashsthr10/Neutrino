"""Security invariant consolidation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.context import ConversationManager, ContextConfig
from src.context.errors import ContextSecurityError
from src.context.manager.validator import Validator
from src.context.models import ContextRequest
from src.context.runtime.conversation_context import ConversationContext, Message


def test_message_store_session_boundary(tmp_path: Path) -> None:
    cfg = ContextConfig(cache_dir=tmp_path / "c")
    cm = ConversationManager(session_id="s1", config=cfg, cache_dir=cfg.resolved_cache_dir())
    cm.append(Message(role="user", content="x", created_at="t", id="m1"))
    db = tmp_path / "c" / "conversation" / "s1" / "messages.sqlite"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("UPDATE messages SET session_id='other' WHERE id='m1'")
        conn.commit()
    with pytest.raises(ContextSecurityError):
        cm._store.get_by_id("m1")


def test_validator_cross_session_metadata() -> None:
    validator = Validator()
    request = ContextRequest(
        task_description="t",
        task_complexity="SIMPLE",
        requesting_agent="planner",
        session_id="s1",
    )
    conv = ConversationContext(
        recent_messages=(
            Message(
                role="user",
                content="x",
                created_at="t",
                id="1",
                metadata={"session_id": "s2"},
            ),
        ),
        summary=None,
        relevant_history=(),
        decisions=(),
        tokens_estimate=1,
        truncated=False,
    )
    with pytest.raises(ContextSecurityError):
        validator.validate(
            request,
            [],
            conv,
            tokens_estimate=1,
            token_budget=8000,
            provenance=[],
            session_id="s1",
        )
