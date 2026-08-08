"""Cache store and invalidation tests."""

from __future__ import annotations

from src.rna.cache.keys import make_cache_key
from src.rna.cache.store import CacheStore


def test_get_or_compute_once(tmp_path) -> None:
    store = CacheStore(tmp_path / "cache", l1_size=16)
    key = make_cache_key(
        repo_fingerprint="fp1",
        subject_hash="file:a.py:abc",
        method_name="get_symbol",
        params={"name": "x"},
    )
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"ok": True}

    v1, hit1 = store.get_or_compute(key, compute)
    v2, hit2 = store.get_or_compute(key, compute)
    assert v1 == {"ok": True}
    assert hit1 is False
    assert hit2 is True
    assert calls["n"] == 1


def test_invalidate_subject(tmp_path) -> None:
    store = CacheStore(tmp_path / "cache")
    key = make_cache_key(
        repo_fingerprint="fp1",
        subject_hash="file:a.py:abc",
        method_name="get_symbol",
        params={"name": "x"},
    )
    store.put(key, {"v": 1})
    assert store.get(key) == {"v": 1}
    deleted = store.invalidate_subject("file:a.py:abc")
    assert deleted == 1
    assert store.get(key) is None


def test_rna_cache_hit_on_symbol(rna_python) -> None:
    r1 = rna_python.get_symbol("parse_request", file_hint="pkg/parser.py")
    r2 = rna_python.get_symbol("parse_request", file_hint="pkg/parser.py")
    assert r1.data
    assert r2.meta.cache_hit is True
