"""Shared fixtures for Context Subsystem tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.context import (
    ContextConfig,
    ContextManager,
    ConversationManager,
    FakeContextManager,
    FakeConversationManager,
)
from src.rna import FakeRna
from src.rna.models import (
    CallEdge,
    ImportEdge,
    SymbolRef,
    TestLink,
)


@pytest.fixture
def fake_rna() -> FakeRna:
    fake = FakeRna()
    fake.files["pkg/parser.py"] = "def parse_request(raw):\n    return raw.split()\n" + (
        "x = 1\n" * 50
    )
    fake.file_names = ["pkg/parser.py", "pkg/router.py", "tests/test_parser.py"]
    fake.symbols["parse_request"] = [
        SymbolRef(
            name="parse_request",
            kind="function",
            file="pkg/parser.py",
            line_start=1,
            line_end=2,
            language="python",
        )
    ]
    fake.import_edges = [
        ImportEdge(from_file="pkg/router.py", to="pkg/parser.py", external=False),
    ]
    fake.callers["parse_request"] = [
        CallEdge(
            caller=SymbolRef(
                name="handle",
                kind="function",
                file="pkg/router.py",
                line_start=4,
                line_end=5,
            ),
            callee_name="parse_request",
            call_site_line=5,
        )
    ]
    fake.tests["pkg/parser.py"] = [
        TestLink(
            test_symbol=None,
            test_file="tests/test_parser.py",
            target="pkg/parser.py",
            relation="direct_import",
            confidence=0.9,
        )
    ]
    return fake


@pytest.fixture
def context_config(tmp_path: Path) -> ContextConfig:
    return ContextConfig(cache_dir=tmp_path / ".context_cache", cache_enabled=True)


@pytest.fixture
def conversation_manager(context_config: ContextConfig) -> ConversationManager:
    return ConversationManager(
        session_id="test-session",
        config=context_config,
        cache_dir=context_config.resolved_cache_dir(),
    )


@pytest.fixture
def fake_conversation_manager() -> FakeConversationManager:
    return FakeConversationManager(session_id="fake-session")


@pytest.fixture
def context_manager(
    fake_rna: FakeRna,
    conversation_manager: ConversationManager,
    context_config: ContextConfig,
) -> ContextManager:
    return ContextManager(
        rna=fake_rna,
        conversation=conversation_manager,
        config=context_config,
    )


@pytest.fixture
def fake_context_manager() -> FakeContextManager:
    return FakeContextManager()
