"""L1 in-memory LRU + L2 on-disk SQLite cache with per-key locks."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, TypeVar

from src.rna.cache.keys import CacheKey

T = TypeVar("T")


class CacheStore:
    def __init__(self, cache_dir: Path, *, l1_size: int = 256, enabled: bool = True) -> None:
        self.cache_dir = cache_dir
        self.enabled = enabled
        self.l1_size = l1_size
        self._l1: OrderedDict[str, Any] = OrderedDict()
        self._l1_lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}
        self._key_locks_guard = threading.Lock()
        self._db_path = cache_dir / "manifest.sqlite"
        self._blobs = cache_dir / "blobs"
        if enabled:
            self._ensure_layout()

    def _ensure_layout(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._blobs.mkdir(parents=True, exist_ok=True)
        gi = self.cache_dir / ".gitignore"
        if not gi.exists():
            gi.write_text("*\n", encoding="utf-8")
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    subject_hash TEXT NOT NULL,
                    method_name TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_version TEXT NOT NULL,
                    inline_json TEXT,
                    blob_ref TEXT,
                    written_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_subject ON cache(subject_hash)"
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _lock_for(self, key: str) -> threading.Lock:
        with self._key_locks_guard:
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
            return self._key_locks[key]

    def get(self, key: CacheKey) -> Any | None:
        if not self.enabled:
            return None
        k = key.as_str()
        with self._l1_lock:
            if k in self._l1:
                self._l1.move_to_end(k)
                return self._l1[k]
        with self._connect() as conn:
            row = conn.execute("SELECT inline_json, blob_ref FROM cache WHERE key=?", (k,)).fetchone()
        if row is None:
            return None
        if row["inline_json"] is not None:
            value = json.loads(row["inline_json"])
        else:
            blob = self._blobs / row["blob_ref"]
            if not blob.is_file():
                return None
            value = json.loads(blob.read_text(encoding="utf-8"))
        with self._l1_lock:
            self._l1[k] = value
            self._l1.move_to_end(k)
            while len(self._l1) > self.l1_size:
                self._l1.popitem(last=False)
        return value

    def put(self, key: CacheKey, value: Any, *, as_blob: bool = False) -> None:
        if not self.enabled:
            return
        k = key.as_str()
        payload = json.dumps(value, default=str)
        inline = None
        blob_ref = None
        if as_blob or len(payload) > 16_384:
            blob_ref = f"{k}.json"
            (self._blobs / blob_ref).write_text(payload, encoding="utf-8")
        else:
            inline = payload
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache
                (key, subject_hash, method_name, tool_name, tool_version, inline_json, blob_ref, written_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    k,
                    key.subject_hash,
                    key.method_name,
                    key.tool_name,
                    key.tool_version,
                    inline,
                    blob_ref,
                    time.time(),
                ),
            )
            conn.commit()
        with self._l1_lock:
            self._l1[k] = value
            self._l1.move_to_end(k)
            while len(self._l1) > self.l1_size:
                self._l1.popitem(last=False)

    def get_or_compute(self, key: CacheKey, compute: Callable[[], T], *, as_blob: bool = False) -> tuple[T, bool]:
        """Compute-once-under-lock. Returns (value, cache_hit)."""
        if not self.enabled:
            return compute(), False
        k = key.as_str()
        lock = self._lock_for(k)
        with lock:
            cached = self.get(key)
            if cached is not None:
                return cached, True  # type: ignore[return-value]
            value = compute()
            self.put(key, value, as_blob=as_blob)
            return value, False

    def invalidate_subject(self, subject_hash: str) -> int:
        if not self.enabled:
            return 0
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, blob_ref FROM cache WHERE subject_hash=?", (subject_hash,)
            ).fetchall()
            conn.execute("DELETE FROM cache WHERE subject_hash=?", (subject_hash,))
            conn.commit()
        for row in rows:
            if row["blob_ref"]:
                blob = self._blobs / row["blob_ref"]
                if blob.is_file():
                    blob.unlink(missing_ok=True)
            with self._l1_lock:
                self._l1.pop(row["key"], None)
        return len(rows)

    def invalidate_all(self) -> None:
        if not self.enabled:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM cache")
            conn.commit()
        for blob in self._blobs.glob("*.json"):
            blob.unlink(missing_ok=True)
        with self._l1_lock:
            self._l1.clear()

    def subjects_for_prefix(self, prefix: str) -> list[str]:
        """Utility for tests / debugging."""
        if not self.enabled:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT subject_hash FROM cache WHERE subject_hash LIKE ?",
                (f"{prefix}%",),
            ).fetchall()
        return [r["subject_hash"] for r in rows]
