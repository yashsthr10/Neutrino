"""get_symbol via provider chain."""

from __future__ import annotations

from src.rna.adapters.registry import LanguageRegistry
from src.rna.models import Confidence, SymbolRef


class SymbolIndex:
    def __init__(self, registry: LanguageRegistry) -> None:
        self.registry = registry

    def get_symbol(
        self, name: str, *, file_hint: str | None = None
    ) -> tuple[list[SymbolRef], Confidence, str | None]:
        language = None
        if file_hint:
            language = self.registry.language_for_path(file_hint)
        if language is None:
            language = self.registry.primary_language()
        providers = self.registry.resolve(language)
        best: list[SymbolRef] = []
        confidence: Confidence = "heuristic"
        reason: str | None = None
        for provider in providers:
            try:
                found = provider.find_symbol(name, file_hint)
            except Exception as exc:  # noqa: BLE001 — degrade tiers
                reason = f"{provider.tier} failed: {exc}"
                continue
            if found:
                best = found
                if provider.tier == "semantic":
                    confidence = "precise"
                elif provider.tier == "whole_program":
                    confidence = "whole_program"
                else:
                    confidence = "heuristic"
                break
        return best, confidence, reason
