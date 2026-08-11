"""Language -> provider chain resolution."""

from __future__ import annotations

import shutil

from src.rna.adapters.base import LanguageProvider, detect_language
from src.rna.adapters.tree_sitter_provider import TreeSitterProvider
from src.rna.config import RnaConfig

LANGUAGE_TOOLS: dict[str, dict[str, list[str]]] = {
    "python": {
        "lsp": ["pylsp", "pyright-langserver"],
        "tier3": ["pycg", "pyan3", "pyreverse"],
    },
    "typescript": {
        "lsp": ["typescript-language-server"],
        "tier3": ["madge", "ts-morph", "dependency-cruiser"],
    },
    "javascript": {
        "lsp": ["typescript-language-server"],
        "tier3": ["madge", "dependency-cruiser"],
    },
    "go": {"lsp": ["gopls"], "tier3": ["go-callgraph"]},
    "cpp": {"lsp": ["clangd"], "tier3": ["clangd", "cscope", "ctags"]},
    "c": {"lsp": ["clangd"], "tier3": ["clangd", "cscope", "ctags"]},
    "rust": {"lsp": ["rust-analyzer"], "tier3": []},
    "java": {"lsp": ["jdtls"], "tier3": []},
}


class LanguageRegistry:
    def __init__(self, config: RnaConfig) -> None:
        self.config = config
        self.repo_root = config.repo_path
        self._chains: dict[str, list[LanguageProvider]] = {}
        self._probe_cache: dict[str, bool] = {}

    def which(self, binary: str) -> bool:
        if binary in self._probe_cache:
            return self._probe_cache[binary]
        found = shutil.which(binary) is not None
        self._probe_cache[binary] = found
        return found

    def resolve(self, language: str) -> list[LanguageProvider]:
        if language in self._chains:
            return self._chains[language]
        chain: list[LanguageProvider] = []
        enabled = set(self.config.enabled_tiers)

        if "structural" in enabled:
            ts = TreeSitterProvider(language, self.repo_root)
            if ts.is_available():
                chain.append(ts)

        if "semantic" in enabled:
            lsp = self._maybe_lsp(language)
            if lsp is not None:
                # LSP first for precision when available
                chain.insert(0, lsp)

        if "whole_program" in enabled:
            tier3 = self._maybe_tier3(language)
            if tier3 is not None:
                chain.append(tier3)

        # Prefer order: semantic (LSP), whole_program, structural for call lookups
        # Reorder: LSP, Tier3, TreeSitter
        ordered: list[LanguageProvider] = []
        for tier in ("semantic", "whole_program", "structural"):
            for p in chain:
                if p.tier == tier and p not in ordered:
                    ordered.append(p)
        for p in chain:
            if p not in ordered:
                ordered.append(p)

        self._chains[language] = ordered
        return ordered

    def _maybe_lsp(self, language: str) -> LanguageProvider | None:
        try:
            from src.rna.adapters.lsp_provider import LspProvider
        except ImportError:
            return None
        tools = LANGUAGE_TOOLS.get(language, {}).get("lsp", [])
        for binary in tools:
            if self.which(binary):
                provider = LspProvider(
                    language, self.repo_root, binary, timeout_ms=self.config.lsp_timeout_ms
                )
                if provider.is_available():
                    return provider
        return None

    def _maybe_tier3(self, language: str) -> LanguageProvider | None:
        try:
            if language == "python":
                from src.rna.adapters.python_tools import PythonTier3Provider

                p = PythonTier3Provider(self.repo_root, timeout_ms=self.config.tier3_timeout_ms)
                return p if p.is_available() else None
            if language in {"javascript", "typescript"}:
                from src.rna.adapters.js_ts_tools import JsTsTier3Provider

                p = JsTsTier3Provider(
                    language, self.repo_root, timeout_ms=self.config.tier3_timeout_ms
                )
                return p if p.is_available() else None
            if language == "go":
                from src.rna.adapters.go_tools import GoTier3Provider

                p = GoTier3Provider(self.repo_root, timeout_ms=self.config.tier3_timeout_ms)
                return p if p.is_available() else None
            if language in {"c", "cpp"}:
                from src.rna.adapters.cpp_tools import CppTier3Provider

                p = CppTier3Provider(
                    language, self.repo_root, timeout_ms=self.config.tier3_timeout_ms
                )
                return p if p.is_available() else None
        except ImportError:
            return None
        return None

    def language_for_path(self, path: str) -> str | None:
        return detect_language(path)

    def primary_language(self) -> str:
        """Guess dominant language from file counts."""
        counts: dict[str, int] = {}
        for p in self.repo_root.rglob("*"):
            if not p.is_file():
                continue
            lang = detect_language(str(p))
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
        if not counts:
            return "python"
        return max(counts, key=counts.get)  # type: ignore[arg-type]
