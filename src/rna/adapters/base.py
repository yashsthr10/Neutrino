"""LanguageProvider protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.rna.models import CallEdge, ImportEdge, SymbolRef, WholeProgramGraph


@runtime_checkable
class LanguageProvider(Protocol):
    """One tier's capability for one language."""

    language: str
    tier: str  # "structural" | "semantic" | "whole_program"

    def is_available(self) -> bool: ...

    def find_symbol(self, name: str, file_hint: str | None) -> list[SymbolRef]: ...

    def find_imports(self, file_path: str) -> list[ImportEdge]: ...

    def find_callers(self, symbol: str, file_hint: str | None) -> list[CallEdge]: ...

    def find_callees(self, symbol: str, file_hint: str | None) -> list[CallEdge]: ...

    def build_whole_program_graph(self, scope: str) -> WholeProgramGraph | None: ...


EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
}


def detect_language(path: str) -> str | None:
    from pathlib import Path

    return EXT_TO_LANGUAGE.get(Path(path).suffix.lower())
