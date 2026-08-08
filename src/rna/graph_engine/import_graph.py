"""get_import_graph via Tier-1 providers."""

from __future__ import annotations

from pathlib import Path

from src.rna.adapters.base import EXT_TO_LANGUAGE, detect_language
from src.rna.adapters.registry import LanguageRegistry
from src.rna.models import ImportEdge, ImportGraph
from src.rna.repo_analyzer.tree import RepoTree


class ImportGraphBuilder:
    def __init__(self, registry: LanguageRegistry, tree: RepoTree) -> None:
        self.registry = registry
        self.tree = tree

    def get_import_graph(self, scope: str | None = None) -> ImportGraph:
        files = self.tree.list_files()
        if scope:
            scope_n = scope.rstrip("/")
            files = [f for f in files if f == scope_n or f.startswith(scope_n + "/")]
        edges: list[ImportEdge] = []
        for f in files:
            lang = detect_language(f)
            if not lang:
                continue
            providers = self.registry.resolve(lang)
            # Prefer structural for imports (fast / sufficient)
            provider = next((p for p in providers if p.tier == "structural"), None)
            if provider is None and providers:
                provider = providers[-1]
            if provider is None:
                continue
            try:
                edges.extend(provider.find_imports(f))
            except Exception:  # noqa: BLE001
                continue
        return ImportGraph(edges=tuple(edges), scope=scope)
