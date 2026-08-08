"""google_search with opt-in gating and TTL cache."""

from __future__ import annotations

import time
from typing import Any

from src.rna.cache.keys import make_cache_key
from src.rna.cache.store import CacheStore
from src.rna.config import RnaConfig
from src.rna.models import WebResult
from src.rna.repo_analyzer.fingerprint import content_hash
from src.rna.web_engine.providers import DuckDuckGoProvider, GoogleCseProvider, WebProvider


class WebSearchEngine:
    def __init__(
        self,
        config: RnaConfig,
        cache: CacheStore,
        *,
        provider: WebProvider | None = None,
    ) -> None:
        self.config = config
        self.cache = cache
        self._provider = provider

    def _get_provider(self) -> WebProvider | None:
        if self._provider is not None:
            return self._provider
        if self.config.web_search_provider == "google_cse":
            if self.config.web_search_api_key and self.config.web_search_cx:
                return GoogleCseProvider(self.config.web_search_api_key, self.config.web_search_cx)
            return None
        if self.config.web_search_provider == "duckduckgo":
            return DuckDuckGoProvider()
        return None

    def search(self, query: str, *, limit: int = 5) -> tuple[list[WebResult], str | None, bool]:
        """Returns (results, error, cache_hit)."""
        if not self.config.web_search_enabled:
            return [], "disabled", False
        provider = self._get_provider()
        if provider is None:
            return [], "disabled", False

        key = make_cache_key(
            repo_fingerprint="web",
            subject_hash=content_hash(query),
            method_name="google_search",
            params={"query": query, "limit": limit, "provider": provider.name},
            tool_name=provider.name,
            tool_version="1",
        )
        cached = self.cache.get(key)
        if cached is not None:
            fetched_at = cached.get("fetched_at", 0)
            if time.time() - fetched_at <= self.config.web_cache_ttl_seconds:
                results = [WebResult(**r) for r in cached["results"]]
                return results, None, True

        try:
            results = provider.search(query, limit=limit)
        except Exception as exc:  # noqa: BLE001
            return [], f"provider_error:{exc}", False

        from dataclasses import asdict

        payload: dict[str, Any] = {
            "results": [asdict(r) for r in results],
            "fetched_at": time.time(),
        }
        self.cache.put(key, payload)
        return results, None, False
