"""Semantic search relevance tests (hash embeddings)."""

from __future__ import annotations

from src.rna import Rna
from src.rna.config import RnaConfig


def test_semantic_search_ranks_parser(python_repo) -> None:
    cfg = RnaConfig(
        repo_path=python_repo,
        cache_dir=python_repo / ".rna_cache",
        enabled_tiers=("structural",),
        embedding_model="hash",
    )
    rna = Rna(cfg)
    result = rna.semantic_search("split request string into tokens", limit=5)
    assert result.data
    files = [h.file for h in result.data]
    # parser.py should be among top hits for this query
    assert any("parser.py" in f for f in files)
    assert result.meta.degraded is True  # hash embeddings
