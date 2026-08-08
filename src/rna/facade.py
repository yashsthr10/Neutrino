"""Rna facade — composes engines and returns RnaResult envelopes."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

from src.rna.adapters.registry import LanguageRegistry
from src.rna.cache.invalidation import Invalidator
from src.rna.cache.keys import make_cache_key
from src.rna.cache.store import CacheStore
from src.rna.config import RnaConfig
from src.rna.graph_engine.call_graph import CallGraphService
from src.rna.graph_engine.import_graph import ImportGraphBuilder
from src.rna.graph_engine.symbol_index import SymbolIndex
from dataclasses import asdict

from src.rna.models import (
    CallEdge,
    FileSlice,
    HLDModel,
    ImportEdge,
    ImportGraph,
    LLDModel,
    RnaMeta,
    RnaResult,
    SearchHit,
    SemanticHit,
    SymbolRef,
    TestLink,
    WebResult,
    WorkflowTrace,
)
from src.rna.observability import timed_call
from src.rna.repo_analyzer.files import FileService
from src.rna.repo_analyzer.fingerprint import content_hash, repo_fingerprint
from src.rna.repo_analyzer.tree import RepoTree
from src.rna.search_engine.lexical import LexicalSearch


class Rna:
    """Read-only knowledge API over a repository."""

    def __init__(self, config: RnaConfig | Path | str) -> None:
        if isinstance(config, (str, Path)):
            config = RnaConfig(repo_path=Path(config))
        self.config = config
        self.repo_path = config.repo_path
        self.tree = RepoTree(self.repo_path, config.ignore_patterns)
        self.files = FileService(
            self.repo_path, self.tree, max_lines_per_file=config.max_lines_per_file
        )
        self.cache = CacheStore(
            config.resolved_cache_dir(),
            l1_size=config.l1_cache_size,
            enabled=config.cache_enabled,
        )
        self.invalidator = Invalidator(self.repo_path, self.cache)
        self.registry = LanguageRegistry(config)
        self.symbol_index = SymbolIndex(self.registry)
        self.import_graph = ImportGraphBuilder(self.registry, self.tree)
        self.call_graph = CallGraphService(self.registry, self.cache)
        self.lexical = LexicalSearch(self.repo_path, self.tree)

        # Lazily constructed Phase 2/3 engines
        self._design = None
        self._test_linker = None
        self._git = None
        self._embeddings = None
        self._web = None

    def _fp(self) -> str:
        fp = repo_fingerprint(self.repo_path)
        self.invalidator.sync_fingerprint(fp)
        return fp

    def invalidate(self, path: str | None = None) -> None:
        if path is None:
            self.invalidator.invalidate_all()
            self.tree.invalidate()
        else:
            self.invalidator.invalidate_path(path)
            self.tree.invalidate()

    def get_file(
        self,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> RnaResult[FileSlice | None]:
        with timed_call("get_file", f"path={path}") as log:
            t0 = time.perf_counter()
            slice_, err, truncated = self.files.get_file(
                path, start_line=start_line, end_line=end_line
            )
            cost = (time.perf_counter() - t0) * 1000
            tokens = len((slice_.content if slice_ else "").split())
            log.error = err
            return RnaResult(
                data=slice_,
                meta=RnaMeta(
                    cost_ms=cost,
                    cache_hit=False,
                    truncated=truncated,
                    error=err,
                    tokens_estimate=tokens,
                ),
            )

    def get_files_with_name(self, pattern: str, *, limit: int = 50) -> RnaResult[list[str]]:
        with timed_call("get_files_with_name", f"pattern={pattern}") as log:
            t0 = time.perf_counter()
            paths = self.files.get_files_with_name(pattern, limit=limit)
            cost = (time.perf_counter() - t0) * 1000
            truncated = len(paths) >= limit
            log.extra["count"] = len(paths)
            return RnaResult(
                data=paths,
                meta=RnaMeta(cost_ms=cost, cache_hit=False, truncated=truncated),
            )

    def get_symbol(
        self, name: str, *, file_hint: str | None = None
    ) -> RnaResult[list[SymbolRef]]:
        with timed_call("get_symbol", f"name={name}") as log:
            t0 = time.perf_counter()
            fp = self._fp()
            subject = (
                self.invalidator.subject_for_file(file_hint)
                if file_hint
                else content_hash(f"repo:{fp}:symbols")
            )
            key = make_cache_key(
                repo_fingerprint=fp,
                subject_hash=subject,
                method_name="get_symbol",
                params={"name": name, "file_hint": file_hint},
            )

            def compute() -> dict:
                syms, conf, reason = self.symbol_index.get_symbol(name, file_hint=file_hint)
                return {
                    "data": [asdict(s) for s in syms],
                    "confidence": conf,
                    "reason": reason,
                    "error": "not_found" if not syms else None,
                }

            payload, hit = self.cache.get_or_compute(key, compute)
            syms = [SymbolRef(**d) for d in payload["data"]]
            cost = (time.perf_counter() - t0) * 1000
            log.cache_hit = hit
            log.confidence = payload["confidence"]
            log.backend_tier = payload["confidence"]
            return RnaResult(
                data=syms,
                meta=RnaMeta(
                    cost_ms=cost,
                    cache_hit=hit,
                    truncated=False,
                    confidence=payload["confidence"],
                    degraded=bool(payload.get("reason")),
                    reason=payload.get("reason"),
                    error=payload.get("error"),
                ),
            )

    def get_import_graph(self, scope: str | None = None) -> RnaResult[ImportGraph]:
        with timed_call("get_import_graph", f"scope={scope}") as log:
            t0 = time.perf_counter()
            fp = self._fp()
            key = make_cache_key(
                repo_fingerprint=fp,
                subject_hash=content_hash(f"imports:{scope or 'ALL'}"),
                method_name="get_import_graph",
                params={"scope": scope},
            )

            def compute() -> dict:
                g = self.import_graph.get_import_graph(scope)
                return {
                    "edges": [asdict(e) for e in g.edges],
                    "scope": g.scope,
                }

            payload, hit = self.cache.get_or_compute(key, compute, as_blob=True)
            edges = tuple(
                ImportEdge(
                    from_file=e["from_file"],
                    to=e["to"],
                    external=e["external"],
                    symbols=tuple(e.get("symbols") or ()),
                )
                for e in payload["edges"]
            )
            graph = ImportGraph(edges=edges, scope=payload["scope"])
            cost = (time.perf_counter() - t0) * 1000
            log.cache_hit = hit
            return RnaResult(
                data=graph,
                meta=RnaMeta(
                    cost_ms=cost,
                    cache_hit=hit,
                    truncated=False,
                    confidence="heuristic",
                ),
            )

    def get_callers(
        self,
        symbol: str,
        *,
        file_hint: str | None = None,
        limit: int | None = None,
    ) -> RnaResult[list[CallEdge]]:
        limit = limit if limit is not None else self.config.max_callers
        with timed_call("get_callers", f"symbol={symbol}") as log:
            t0 = time.perf_counter()
            edges, conf, truncated, reason = self.call_graph.get_callers(
                symbol, file_hint=file_hint, limit=limit
            )
            cost = (time.perf_counter() - t0) * 1000
            log.confidence = conf
            log.backend_tier = conf
            log.degraded = conf == "heuristic"
            return RnaResult(
                data=edges,
                meta=RnaMeta(
                    cost_ms=cost,
                    cache_hit=False,
                    truncated=truncated,
                    confidence=conf,
                    degraded=conf == "heuristic" or bool(reason),
                    reason=reason,
                    error="not_found" if not edges else None,
                ),
            )

    def search(
        self,
        query: str,
        *,
        glob: str | None = None,
        limit: int = 50,
        regex: bool = False,
    ) -> RnaResult[list[SearchHit]]:
        with timed_call("search", f"query={query[:80]}") as log:
            t0 = time.perf_counter()
            hits, degraded, reason = self.lexical.search(
                query, glob=glob, limit=limit, regex=regex
            )
            cost = (time.perf_counter() - t0) * 1000
            log.degraded = degraded
            return RnaResult(
                data=hits,
                meta=RnaMeta(
                    cost_ms=cost,
                    cache_hit=False,
                    truncated=len(hits) >= limit,
                    degraded=degraded,
                    reason=reason,
                ),
            )

    # --- Phase 2 methods ---

    def _ensure_design(self):
        if self._design is None:
            from src.rna.graph_engine.design_recovery import DesignRecovery

            self._design = DesignRecovery(
                self.registry,
                self.tree,
                self.import_graph,
                self.call_graph,
                self.symbol_index,
                max_depth=self.config.max_workflow_depth,
            )
        return self._design

    def _ensure_test_linker(self):
        if self._test_linker is None:
            from src.rna.git_analyzer.history import GitHistory
            from src.rna.graph_engine.test_linker import TestLinker

            self._git = GitHistory(self.repo_path)
            self._test_linker = TestLinker(
                self.repo_path, self.tree, self.import_graph, self._git, self.registry
            )
        return self._test_linker

    def get_tests(self, target: str) -> RnaResult[list[TestLink]]:
        with timed_call("get_tests", f"target={target}") as log:
            t0 = time.perf_counter()
            links = self._ensure_test_linker().get_tests(target)
            cost = (time.perf_counter() - t0) * 1000
            log.extra["count"] = len(links)
            return RnaResult(
                data=links,
                meta=RnaMeta(
                    cost_ms=cost,
                    cache_hit=False,
                    truncated=False,
                    error="not_found" if not links else None,
                ),
            )

    def get_workflow(
        self, entrypoint: str, *, max_depth: int = 4
    ) -> RnaResult[WorkflowTrace]:
        with timed_call("get_workflow", f"entrypoint={entrypoint}") as log:
            t0 = time.perf_counter()
            trace = self._ensure_design().get_workflow(entrypoint, max_depth=max_depth)
            cost = (time.perf_counter() - t0) * 1000
            return RnaResult(
                data=trace,
                meta=RnaMeta(
                    cost_ms=cost,
                    cache_hit=False,
                    truncated=trace.truncated_by_depth,
                    confidence="heuristic",
                ),
            )

    def get_hld(
        self,
        *,
        scope: str | None = None,
        format: Literal["json", "mermaid"] = "json",
    ) -> RnaResult[HLDModel]:
        with timed_call("get_hld", f"scope={scope}") as log:
            t0 = time.perf_counter()
            model = self._ensure_design().get_hld(scope=scope, format=format)
            cost = (time.perf_counter() - t0) * 1000
            log.cache_hit = False
            return RnaResult(
                data=model,
                meta=RnaMeta(
                    cost_ms=cost,
                    cache_hit=False,
                    truncated=False,
                    confidence="heuristic",
                ),
            )

    def get_lld(
        self,
        scope: str,
        *,
        format: Literal["json", "mermaid"] = "json",
    ) -> RnaResult[LLDModel]:
        with timed_call("get_lld", f"scope={scope}") as log:
            t0 = time.perf_counter()
            model, degraded, reason, conf = self._ensure_design().get_lld(
                scope, format=format
            )
            cost = (time.perf_counter() - t0) * 1000
            log.degraded = degraded
            log.confidence = conf
            log.backend_tier = conf
            return RnaResult(
                data=model,
                meta=RnaMeta(
                    cost_ms=cost,
                    cache_hit=False,
                    truncated=False,
                    confidence=conf,
                    degraded=degraded,
                    reason=reason,
                ),
            )

    # --- Phase 3 methods ---

    def _ensure_embeddings(self):
        if self._embeddings is None:
            from src.rna.embedding_engine.semantic_search import SemanticSearchEngine

            self._embeddings = SemanticSearchEngine(self.config, self.tree, self.registry)
        return self._embeddings

    def _ensure_web(self):
        if self._web is None:
            from src.rna.web_engine.web_search import WebSearchEngine

            self._web = WebSearchEngine(self.config, self.cache)
        return self._web

    def semantic_search(self, query: str, *, limit: int = 10) -> RnaResult[list[SemanticHit]]:
        with timed_call("semantic_search", f"query={query[:80]}") as log:
            t0 = time.perf_counter()
            hits, degraded, reason = self._ensure_embeddings().search(query, limit=limit)
            cost = (time.perf_counter() - t0) * 1000
            log.degraded = degraded
            return RnaResult(
                data=hits,
                meta=RnaMeta(
                    cost_ms=cost,
                    cache_hit=False,
                    truncated=len(hits) >= limit,
                    degraded=degraded,
                    reason=reason,
                ),
            )

    def google_search(self, query: str, *, limit: int = 5) -> RnaResult[list[WebResult]]:
        summary = "query=<redacted>" if not self.config.log_web_query_text else f"query={query[:80]}"
        with timed_call("google_search", summary) as log:
            t0 = time.perf_counter()
            results, err, hit = self._ensure_web().search(query, limit=limit)
            cost = (time.perf_counter() - t0) * 1000
            log.network_egress = err is None and not hit and bool(results)
            log.cache_hit = hit
            log.error = err
            log.provider = self.config.web_search_provider
            return RnaResult(
                data=results,
                meta=RnaMeta(
                    cost_ms=cost,
                    cache_hit=hit,
                    truncated=len(results) >= limit,
                    error=err,
                    reason="web search disabled" if err == "disabled" else None,
                ),
            )

    def warm(self, *, only: Literal["embeddings"] | None = "embeddings") -> None:
        if only in (None, "embeddings"):
            self._ensure_embeddings().warm()
