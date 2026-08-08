"""semantic_search orchestration."""

from __future__ import annotations

from src.rna.adapters.registry import LanguageRegistry
from src.rna.config import RnaConfig
from src.rna.embedding_engine.chunker import Chunker
from src.rna.embedding_engine.vector_store import VectorStore
from src.rna.models import SemanticHit
from src.rna.repo_analyzer.tree import RepoTree


class SemanticSearchEngine:
    def __init__(
        self,
        config: RnaConfig,
        tree: RepoTree,
        registry: LanguageRegistry,
    ) -> None:
        self.config = config
        self.tree = tree
        self.registry = registry
        self.chunker = Chunker(config.repo_path, tree, registry)
        self.store = VectorStore(config.resolved_cache_dir(), model=config.embedding_model)

    def warm(self) -> None:
        chunks = self.chunker.chunk_repo()
        self.store.upsert_chunks(chunks)

    def search(self, query: str, *, limit: int = 10) -> tuple[list[SemanticHit], bool, str | None]:
        degraded = False
        reason = None
        if self.store.count() == 0:
            self.warm()
            degraded = self.config.embedding_model == "hash"
            if degraded:
                reason = "using offline hash embeddings (install rna-embeddings for sentence-transformers)"
        elif self.config.embedding_model == "hash":
            degraded = True
            reason = "using offline hash embeddings"
        # Incremental: ensure new files are chunked
        self.store.upsert_chunks(self.chunker.chunk_repo())
        results = self.store.query(query, limit=limit)
        hits = [
            SemanticHit(
                file=ch.file,
                symbol=ch.symbol,
                start_line=ch.start_line,
                end_line=ch.end_line,
                snippet=ch.content[:500],
                score=score,
            )
            for ch, score in results
        ]
        return hits, degraded, reason
