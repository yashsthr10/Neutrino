"""Web search opt-in gating and TTL cache."""

from __future__ import annotations

import pytest

from src.rna import Rna
from src.rna.config import RnaConfig
from src.rna.models import WebResult
from src.rna.web_engine.providers import MockProvider
from src.rna.web_engine.web_search import WebSearchEngine


def test_disabled_returns_error_without_network(python_repo) -> None:
    cfg = RnaConfig(
        repo_path=python_repo,
        cache_dir=python_repo / ".rna_cache",
        web_search_enabled=False,
    )
    rna = Rna(cfg)
    # Force provider to raise if called
    mock = MockProvider()
    rna._web = WebSearchEngine(cfg, rna.cache, provider=mock)  # noqa: SLF001
    result = rna.google_search("python list docs")
    assert result.meta.error == "disabled"
    assert result.data == []
    assert mock.calls == 0


def test_enabled_uses_provider_and_caches(python_repo) -> None:
    cfg = RnaConfig(
        repo_path=python_repo,
        cache_dir=python_repo / ".rna_cache",
        web_search_enabled=True,
        web_search_provider="mock",
    )
    mock = MockProvider(
        [
            WebResult(
                title="Docs",
                url="https://example.com",
                snippet="hello",
                source="mock",
                fetched_at="2020-01-01T00:00:00+00:00",
            )
        ]
    )
    engine = WebSearchEngine(cfg, __import__("src.rna.cache.store", fromlist=["CacheStore"]).CacheStore(python_repo / ".rna_cache"), provider=mock)
    r1, err1, hit1 = engine.search("q", limit=3)
    r2, err2, hit2 = engine.search("q", limit=3)
    assert err1 is None and err2 is None
    assert hit1 is False and hit2 is True
    assert mock.calls == 1
    assert r1[0].title == "Docs"
