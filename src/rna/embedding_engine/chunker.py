"""Semantic chunking on tree-sitter node boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.rna.adapters.base import detect_language
from src.rna.adapters.registry import LanguageRegistry
from src.rna.repo_analyzer.tree import RepoTree


@dataclass(frozen=True, slots=True)
class Chunk:
    file: str
    symbol: str | None
    start_line: int
    end_line: int
    content: str


class Chunker:
    def __init__(self, repo_root: Path, tree: RepoTree, registry: LanguageRegistry) -> None:
        self.repo_root = repo_root
        self.tree = tree
        self.registry = registry

    def chunk_repo(self) -> list[Chunk]:
        chunks: list[Chunk] = []
        for rel in self.tree.list_files():
            lang = detect_language(rel)
            if not lang:
                continue
            chunks.extend(self.chunk_file(rel, lang))
        return chunks

    def chunk_file(self, rel: str, lang: str | None = None) -> list[Chunk]:
        lang = lang or detect_language(rel)
        if not lang:
            return []
        path = self.repo_root / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        providers = self.registry.resolve(lang)
        structural = next((p for p in providers if p.tier == "structural"), None)
        chunks: list[Chunk] = []
        if structural is not None and hasattr(structural, "symbols_in_file"):
            lines = text.splitlines()
            for sym in structural.symbols_in_file(rel):  # type: ignore[attr-defined]
                start = max(1, sym.line_start)
                end = min(len(lines), sym.line_end)
                content = "\n".join(lines[start - 1 : end])
                if content.strip():
                    chunks.append(
                        Chunk(
                            file=rel,
                            symbol=sym.name,
                            start_line=start,
                            end_line=end,
                            content=content,
                        )
                    )
        if not chunks:
            # whole-file fallback (bounded)
            content = "\n".join(text.splitlines()[:200])
            chunks.append(
                Chunk(
                    file=rel,
                    symbol=None,
                    start_line=1,
                    end_line=min(200, len(text.splitlines()) or 1),
                    content=content,
                )
            )
        return chunks
