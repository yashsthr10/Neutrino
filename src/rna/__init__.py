"""RNA — Research & Analysis engine for coding agents."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from src.rna.config import RnaConfig
from src.rna.errors import RnaConfigError, RnaError, RnaSecurityError
from src.rna.facade import Rna
from src.rna.models import (
    CallEdge,
    FileSlice,
    HLDGranularity,
    HLDModel,
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


@runtime_checkable
class RnaPort(Protocol):
    """Read-only knowledge API over a repository. No side effects, no LLM calls."""

    def get_symbol(
        self, name: str, *, file_hint: str | None = None
    ) -> RnaResult[list[SymbolRef]]: ...

    def get_file(
        self,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> RnaResult[FileSlice | None]: ...

    def get_files_with_name(self, pattern: str, *, limit: int = 50) -> RnaResult[list[str]]: ...

    def get_import_graph(self, scope: str | None = None) -> RnaResult[ImportGraph]: ...

    def get_callers(
        self, symbol: str, *, file_hint: str | None = None, limit: int = 25
    ) -> RnaResult[list[CallEdge]]: ...

    def get_tests(self, target: str) -> RnaResult[list[TestLink]]: ...

    def get_workflow(
        self,
        entrypoint: str,
        *,
        max_depth: int = 4,
        format: Literal["json", "mermaid"] = "json",
    ) -> RnaResult[WorkflowTrace]: ...

    def get_hld(
        self,
        *,
        scope: str | None = None,
        format: Literal["json", "mermaid"] = "json",
        granularity: Literal["coarse", "module", "fine", "file"] = "module",
    ) -> RnaResult[HLDModel]: ...

    def get_lld(
        self, scope: str, *, format: Literal["json", "mermaid"] = "json"
    ) -> RnaResult[LLDModel]: ...

    def search(
        self, query: str, *, glob: str | None = None, limit: int = 50
    ) -> RnaResult[list[SearchHit]]: ...

    def semantic_search(self, query: str, *, limit: int = 10) -> RnaResult[list[SemanticHit]]: ...

    def google_search(self, query: str, *, limit: int = 5) -> RnaResult[list[WebResult]]: ...


__all__ = [
    "Rna",
    "RnaPort",
    "RnaConfig",
    "RnaError",
    "RnaSecurityError",
    "RnaConfigError",
    "RnaResult",
    "RnaMeta",
    "SymbolRef",
    "FileSlice",
    "ImportGraph",
    "CallEdge",
    "TestLink",
    "WorkflowTrace",
    "HLDGranularity",
    "HLDModel",
    "LLDModel",
    "SearchHit",
    "SemanticHit",
    "WebResult",
]
