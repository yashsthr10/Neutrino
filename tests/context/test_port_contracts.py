"""Port contract tests: real and fake implementations share shape."""

from __future__ import annotations

import pytest

from src.context import (
    ContextManagerPort,
    ConversationManagerPort,
    ContextRequest,
    FakeContextManager,
    FakeConversationManager,
)
from src.context.runtime.conversation_context import Message


@pytest.mark.parametrize("impl_name", ["real", "fake"])
def test_context_manager_port(
    impl_name: str, context_manager, fake_context_manager: FakeContextManager
) -> None:
    impl: ContextManagerPort = (
        context_manager if impl_name == "real" else fake_context_manager
    )
    assert isinstance(impl, ContextManagerPort)
    result = impl.resolve(
        ContextRequest(
            task_description="add caching to pkg/parser.py",
            task_complexity="MEDIUM",
            requesting_agent="planner",
            file_hints=("pkg/parser.py",),
        )
    )
    assert hasattr(result, "data")
    assert hasattr(result, "meta")


@pytest.mark.parametrize("impl_name", ["real", "fake"])
def test_conversation_manager_port(
    impl_name: str, conversation_manager, fake_conversation_manager: FakeConversationManager
) -> None:
    impl: ConversationManagerPort = (
        conversation_manager if impl_name == "real" else fake_conversation_manager
    )
    assert isinstance(impl, ConversationManagerPort)
    impl.append(Message(role="user", content="hi", created_at="t"))
    recent = impl.get_recent(n=5)
    assert isinstance(recent.data, list)


def test_agent_layer_shaped_smoke(fake_context_manager, fake_conversation_manager) -> None:
    def agent_step(cm: ContextManagerPort, conv: ConversationManagerPort) -> str:
        conv.append(Message(role="user", content="do work", created_at="t"))
        pkg = cm.resolve(
            ContextRequest(
                task_description="do work",
                task_complexity="SIMPLE",
                requesting_agent="coder",
            )
        )
        return pkg.data.request.task_description

    assert agent_step(fake_context_manager, fake_conversation_manager) == "do work"
