"""Pluggable web search providers."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from src.rna.models import WebResult


class WebProvider(Protocol):
    name: str

    def search(self, query: str, *, limit: int = 5) -> list[WebResult]: ...


@dataclass
class GoogleCseProvider:
    api_key: str
    cx: str
    name: str = "google_cse"

    def search(self, query: str, *, limit: int = 5) -> list[WebResult]:
        params = urllib.parse.urlencode(
            {
                "key": self.api_key,
                "cx": self.cx,
                "q": query,
                "num": min(limit, 10),
            }
        )
        url = f"https://www.googleapis.com/customsearch/v1?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "rna-web-engine/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — explicit egress
            data = json.loads(resp.read().decode())
        now = datetime.now(timezone.utc).isoformat()
        results: list[WebResult] = []
        for item in data.get("items", [])[:limit]:
            results.append(
                WebResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    source=self.name,
                    fetched_at=now,
                )
            )
        return results


@dataclass
class DuckDuckGoProvider:
    """HTML-lite Instant Answer API (no key)."""

    name: str = "duckduckgo"

    def search(self, query: str, *, limit: int = 5) -> list[WebResult]:
        params = urllib.parse.urlencode(
            {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        )
        url = f"https://api.duckduckgo.com/?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "rna-web-engine/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
        now = datetime.now(timezone.utc).isoformat()
        results: list[WebResult] = []
        if data.get("AbstractText"):
            results.append(
                WebResult(
                    title=data.get("Heading") or query,
                    url=data.get("AbstractURL") or "",
                    snippet=data.get("AbstractText") or "",
                    source=self.name,
                    fetched_at=now,
                )
            )
        for topic in data.get("RelatedTopics", [])[: limit - len(results)]:
            if isinstance(topic, dict) and "Text" in topic:
                results.append(
                    WebResult(
                        title=topic.get("Text", "")[:80],
                        url=topic.get("FirstURL", ""),
                        snippet=topic.get("Text", ""),
                        source=self.name,
                        fetched_at=now,
                    )
                )
        return results[:limit]


class MockProvider:
    """Test-only provider."""

    name = "mock"

    def __init__(self, results: list[WebResult] | None = None) -> None:
        self.results = results or []
        self.calls = 0

    def search(self, query: str, *, limit: int = 5) -> list[WebResult]:
        self.calls += 1
        return list(self.results)[:limit]
