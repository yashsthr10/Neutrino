"""PackageCache — thin wrapper over rna.cache.store.CacheStore."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TypeVar

from src.rna.cache.keys import CacheKey, make_cache_key
from src.rna.cache.store import CacheStore
from src.rna.repo_analyzer.fingerprint import content_hash

T = TypeVar("T")


class PackageCache:
    def __init__(
        self,
        cache_dir: Path,
        *,
        l1_size: int = 256,
        enabled: bool = True,
    ) -> None:
        packages_dir = cache_dir / "packages"
        packages_dir.mkdir(parents=True, exist_ok=True)
        self._store = CacheStore(packages_dir, l1_size=l1_size, enabled=enabled)

    def make_key(
        self,
        *,
        repo_fingerprint: str,
        conversation_state_hash: str,
        request_fingerprint: str,
    ) -> CacheKey:
        return make_cache_key(
            repo_fingerprint=repo_fingerprint,
            subject_hash=content_hash(f"{conversation_state_hash}:{request_fingerprint}"),
            method_name="context.resolve",
            params={"request": request_fingerprint},
            tool_name="context",
            tool_version="1",
        )

    def get_or_compute(
        self, key: CacheKey, compute: Callable[[], T], *, as_blob: bool = True
    ) -> tuple[T, bool]:
        return self._store.get_or_compute(key, compute, as_blob=as_blob)

    def put(self, key: CacheKey, value: Any, *, as_blob: bool = True) -> None:
        self._store.put(key, value, as_blob=as_blob)

    def get(self, key: CacheKey) -> Any | None:
        return self._store.get(key)

    def invalidate_all(self) -> None:
        self._store.invalidate_all()

    def invalidate_subject(self, subject_hash: str) -> int:
        return self._store.invalidate_subject(subject_hash)
