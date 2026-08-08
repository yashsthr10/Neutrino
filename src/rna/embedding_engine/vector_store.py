"""Local vector store — hash embeddings by default; optional sentence-transformers."""

from __future__ import annotations

import hashlib
import math
import sqlite3
import struct
from pathlib import Path
from typing import Iterable

from src.rna.embedding_engine.chunker import Chunk


def _hash_embed(text: str, dim: int = 256) -> list[float]:
    vec = [0.0] * dim
    tokens = text.lower().split()
    if not tokens:
        return vec
    for tok in tokens:
        h = hashlib.sha256(tok.encode()).digest()
        for i in range(0, min(len(h), dim // 4 * 4), 4):
            idx = struct.unpack_from("<I", h, i)[0] % dim
            vec[idx] += 1.0
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class VectorStore:
    def __init__(self, cache_dir: Path, *, model: str = "hash") -> None:
        self.cache_dir = cache_dir
        self.model = model
        self.dir = cache_dir / "embeddings"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "chunks.sqlite"
        self._st_model = None
        self._ensure()

    def _ensure(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file TEXT NOT NULL,
                    symbol TEXT,
                    start_line INTEGER,
                    end_line INTEGER,
                    content_hash TEXT NOT NULL,
                    content TEXT NOT NULL,
                    vector BLOB NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file)")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _embed(self, text: str) -> list[float]:
        if self.model == "sentence-transformers":
            try:
                if self._st_model is None:
                    from sentence_transformers import SentenceTransformer

                    self._st_model = SentenceTransformer("all-MiniLM-L6-v2")
                vec = self._st_model.encode(text, normalize_embeddings=True)
                return [float(x) for x in vec]
            except Exception:
                return _hash_embed(text)
        return _hash_embed(text)

    @staticmethod
    def _pack(vec: list[float]) -> bytes:
        return struct.pack(f"{len(vec)}f", *vec)

    @staticmethod
    def _unpack(blob: bytes) -> list[float]:
        n = len(blob) // 4
        return list(struct.unpack(f"{n}f", blob))

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks")
            conn.commit()

    def upsert_chunks(self, chunks: Iterable[Chunk]) -> int:
        count = 0
        with self._connect() as conn:
            for ch in chunks:
                content_hash = hashlib.sha256(ch.content.encode()).hexdigest()
                existing = conn.execute(
                    "SELECT id FROM chunks WHERE file=? AND start_line=? AND end_line=? AND content_hash=?",
                    (ch.file, ch.start_line, ch.end_line, content_hash),
                ).fetchone()
                if existing:
                    continue
                # remove stale for same span
                conn.execute(
                    "DELETE FROM chunks WHERE file=? AND start_line=? AND end_line=?",
                    (ch.file, ch.start_line, ch.end_line),
                )
                vec = self._embed(ch.content)
                conn.execute(
                    """
                    INSERT INTO chunks (file, symbol, start_line, end_line, content_hash, content, vector)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ch.file,
                        ch.symbol,
                        ch.start_line,
                        ch.end_line,
                        content_hash,
                        ch.content,
                        self._pack(vec),
                    ),
                )
                count += 1
            conn.commit()
        return count

    def query(self, text: str, *, limit: int = 10) -> list[tuple[Chunk, float]]:
        q = self._embed(text)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT file, symbol, start_line, end_line, content, vector FROM chunks"
            ).fetchall()
        scored: list[tuple[Chunk, float]] = []
        for row in rows:
            vec = self._unpack(row["vector"])
            score = _cosine(q, vec)
            scored.append(
                (
                    Chunk(
                        file=row["file"],
                        symbol=row["symbol"],
                        start_line=row["start_line"],
                        end_line=row["end_line"],
                        content=row["content"],
                    ),
                    score,
                )
            )
        scored.sort(key=lambda t: -t[1])
        return scored[:limit]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()
        return int(row["c"] if row else 0)
