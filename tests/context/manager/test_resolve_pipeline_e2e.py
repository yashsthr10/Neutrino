"""Context Manager resolve pipeline e2e with FakeRna."""

from __future__ import annotations

from src.context import ContextManager, ContextManagerPort, ContextRequest
from src.context.manager.compressor import Compressor
from src.context.manager.ranker import Ranker
from src.context.config import ContextConfig
from src.context.runtime.conversation_context import ConversationContext
from src.context.runtime.repository_context import RepositoryContextItem
from src.rna.models import FileSlice


def test_satisfies_port(context_manager: ContextManager) -> None:
    assert isinstance(context_manager, ContextManagerPort)


def test_resolve_pipeline(context_manager: ContextManager) -> None:
    result = context_manager.resolve(
        ContextRequest(
            task_description="add caching to pkg/parser.py",
            task_complexity="MEDIUM",
            requesting_agent="planner",
            file_hints=("pkg/parser.py",),
            symbol_hints=("parse_request",),
            session_id="test-session",
        )
    )
    assert result.data.repository.items
    kinds = {i.kind for i in result.data.repository.items}
    assert "file" in kinds or "symbol" in kinds or "test_link" in kinds
    assert result.meta.cache_hit is False
    assert result.data.tokens_estimate <= result.data.token_budget


def test_resolve_cache_hit(context_manager: ContextManager) -> None:
    req = ContextRequest(
        task_description="add caching to pkg/parser.py",
        task_complexity="MEDIUM",
        requesting_agent="planner",
        file_hints=("pkg/parser.py",),
        symbol_hints=("parse_request",),
    )
    first = context_manager.resolve(req)
    rna_calls_first = context_manager.last_rna_calls
    assert rna_calls_first > 0
    second = context_manager.resolve(req)
    assert second.meta.cache_hit is True
    assert context_manager.last_rna_calls == 0


def test_ranker_deterministic() -> None:
    cfg = ContextConfig()
    ranker = Ranker(cfg)
    items = [
        RepositoryContextItem(
            kind="file",
            payload=FileSlice("a.py", 1, 2, "a", 2, False),
            relevance=0.0,
            tokens_estimate=2,
            source_method="get_file",
        ),
        RepositoryContextItem(
            kind="symbol",
            payload="x",
            relevance=0.0,
            tokens_estimate=2,
            source_method="get_symbol",
        ),
    ]
    req = ContextRequest(
        task_description="t",
        task_complexity="SIMPLE",
        requesting_agent="planner",
        file_hints=("a.py",),
    )
    a = [(i.kind, i.relevance) for i in ranker.rank(items, req)]
    b = [(i.kind, i.relevance) for i in ranker.rank(items, req)]
    assert a == b


def test_compressor_max_files() -> None:
    cfg = ContextConfig(max_files=1, max_context_tokens=10_000)
    compressor = Compressor(cfg)
    items = [
        RepositoryContextItem(
            kind="file",
            payload=FileSlice(f"f{i}.py", 1, 1, "hi", 1, False),
            relevance=1.0 - i * 0.1,
            tokens_estimate=2,
            source_method="get_file",
        )
        for i in range(3)
    ]
    conv = ConversationContext(
        recent_messages=(),
        summary=None,
        relevant_history=(),
        decisions=(),
        tokens_estimate=0,
        truncated=False,
    )
    kept, _, provenance, truncated = compressor.compress(items, conv)
    assert truncated is True
    assert sum(1 for i in kept if i.kind == "file") <= 1
    assert any("max_files" in p for p in provenance)
