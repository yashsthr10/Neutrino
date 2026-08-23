"""FakeRna test double — scripted, deterministic, no I/O."""

from __future__ import annotations

from typing import Literal

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


class FakeRna:
    """Scripted RnaPort implementation."""

    def __init__(self) -> None:
        self.symbols: dict[str, list[SymbolRef]] = {}
        self.files: dict[str, str] = {}
        self.file_names: list[str] = []
        self.import_edges: list[ImportEdge] = []
        self.callers: dict[str, list[CallEdge]] = {}
        self.tests: dict[str, list[TestLink]] = {}
        self.workflows: dict[str, WorkflowTrace] = {}
        self.hld = HLDModel(nodes=(), edges=())
        self.lld: dict[str, LLDModel] = {}
        self.search_hits: list[SearchHit] = []
        self.semantic_hits: list[SemanticHit] = []
        self.web_results: list[WebResult] = []
        self.web_enabled = True

    def get_symbol(self, name: str, *, file_hint: str | None = None) -> RnaResult[list[SymbolRef]]:
        data = list(self.symbols.get(name, []))
        return RnaResult(
            data=data,
            meta=RnaMeta(
                cost_ms=0.0,
                cache_hit=True,
                truncated=False,
                confidence="precise",
                error=None if data else "not_found",
            ),
        )

    def get_file(
        self,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> RnaResult[FileSlice | None]:
        content = self.files.get(path)
        if content is None:
            return RnaResult(
                data=None,
                meta=RnaMeta(cost_ms=0.0, cache_hit=True, truncated=False, error="not_found"),
            )
        lines = content.splitlines(keepends=True)
        total = len(lines)
        start = start_line or 1
        end = end_line or total
        slice_content = "".join(lines[start - 1 : end])
        return RnaResult(
            data=FileSlice(
                path=path,
                start_line=start,
                end_line=end,
                content=slice_content,
                total_lines=total,
                truncated=False,
            ),
            meta=RnaMeta(cost_ms=0.0, cache_hit=True, truncated=False),
        )

    def get_files_with_name(self, pattern: str, *, limit: int = 50) -> RnaResult[list[str]]:
        import fnmatch

        matched = [
            f
            for f in self.file_names
            if pattern.lower() in f.lower() or fnmatch.fnmatch(f, pattern)
        ][:limit]
        return RnaResult(
            data=matched,
            meta=RnaMeta(cost_ms=0.0, cache_hit=True, truncated=len(matched) >= limit),
        )

    def get_import_graph(self, scope: str | None = None) -> RnaResult[ImportGraph]:
        edges = self.import_edges
        if scope:
            edges = [e for e in edges if e.from_file.startswith(scope)]
        return RnaResult(
            data=ImportGraph(edges=tuple(edges), scope=scope),
            meta=RnaMeta(cost_ms=0.0, cache_hit=True, truncated=False, confidence="heuristic"),
        )

    def get_callers(
        self, symbol: str, *, file_hint: str | None = None, limit: int = 25
    ) -> RnaResult[list[CallEdge]]:
        data = list(self.callers.get(symbol, []))[:limit]
        return RnaResult(
            data=data,
            meta=RnaMeta(
                cost_ms=0.0,
                cache_hit=True,
                truncated=False,
                confidence="precise",
                error=None if data else "not_found",
            ),
        )

    def get_tests(self, target: str) -> RnaResult[list[TestLink]]:
        data = list(self.tests.get(target, []))
        return RnaResult(
            data=data,
            meta=RnaMeta(
                cost_ms=0.0,
                cache_hit=True,
                truncated=False,
                error=None if data else "not_found",
            ),
        )

    def get_workflow(self, entrypoint: str, *, max_depth: int = 4) -> RnaResult[WorkflowTrace]:
        data = self.workflows.get(
            entrypoint,
            WorkflowTrace(entrypoint=entrypoint, steps=(), truncated_by_depth=False),
        )
        return RnaResult(
            data=data,
            meta=RnaMeta(cost_ms=0.0, cache_hit=True, truncated=data.truncated_by_depth),
        )

    def get_hld(
        self,
        *,
        scope: str | None = None,
        format: Literal["json", "mermaid"] = "json",
        granularity: Literal["coarse", "module", "fine", "file"] = "module",
    ) -> RnaResult[HLDModel]:
        model = self.hld
        if format == "mermaid" and model.mermaid is None:
            model = HLDModel(
                nodes=model.nodes,
                edges=model.edges,
                mermaid="graph TD\n  A-->B",
            )
        return RnaResult(
            data=model,
            meta=RnaMeta(cost_ms=0.0, cache_hit=True, truncated=False, confidence="heuristic"),
        )

    def get_lld(
        self, scope: str, *, format: Literal["json", "mermaid"] = "json"
    ) -> RnaResult[LLDModel]:
        model = self.lld.get(scope, LLDModel(scope=scope, nodes=(), edges=()))
        if format == "mermaid" and model.mermaid is None:
            model = LLDModel(
                scope=scope,
                nodes=model.nodes,
                edges=model.edges,
                mermaid="graph TD\n  A-->B",
            )
        return RnaResult(
            data=model,
            meta=RnaMeta(cost_ms=0.0, cache_hit=True, truncated=False, confidence="whole_program"),
        )

    def search(
        self, query: str, *, glob: str | None = None, limit: int = 50, regex: bool = False
    ) -> RnaResult[list[SearchHit]]:
        hits = [h for h in self.search_hits if query.lower() in h.snippet.lower()][:limit]
        return RnaResult(
            data=hits,
            meta=RnaMeta(cost_ms=0.0, cache_hit=True, truncated=len(hits) >= limit),
        )

    def semantic_search(self, query: str, *, limit: int = 10) -> RnaResult[list[SemanticHit]]:
        return RnaResult(
            data=list(self.semantic_hits)[:limit],
            meta=RnaMeta(cost_ms=0.0, cache_hit=True, truncated=False),
        )

    def google_search(self, query: str, *, limit: int = 5) -> RnaResult[list[WebResult]]:
        if not self.web_enabled:
            return RnaResult(
                data=[],
                meta=RnaMeta(
                    cost_ms=0.0,
                    cache_hit=False,
                    truncated=False,
                    error="disabled",
                    reason="web search disabled",
                ),
            )
        return RnaResult(
            data=list(self.web_results)[:limit],
            meta=RnaMeta(cost_ms=0.0, cache_hit=True, truncated=False),
        )
