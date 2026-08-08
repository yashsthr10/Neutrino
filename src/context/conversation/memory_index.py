"""Keyword memory index over conversation messages (FTS / inverted index)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from src.context.runtime.conversation_context import Message

_TOKEN_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text) if len(t) > 1]


class MemoryIndex:
    def __init__(self, db_path: Path, session_id: str) -> None:
        self.session_id = session_id
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS keyword_index (
                    message_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    token TEXT NOT NULL,
                    PRIMARY KEY (message_id, token)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kw_token ON keyword_index(session_id, token)"
            )
            conn.commit()

    def index_message(self, message: Message) -> None:
        tokens = set(_tokenize(message.content))
        if not tokens:
            return
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM keyword_index WHERE message_id=? AND session_id=?",
                (message.id, self.session_id),
            )
            conn.executemany(
                "INSERT OR IGNORE INTO keyword_index (message_id, session_id, token) VALUES (?, ?, ?)",
                [(message.id, self.session_id, t) for t in tokens],
            )
            conn.commit()

    def search(self, query: str, *, limit: int = 10) -> list[tuple[str, float]]:
        """Return (message_id, score) ranked by keyword overlap."""
        tokens = set(_tokenize(query))
        if not tokens:
            return []
        placeholders = ",".join("?" * len(tokens))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT message_id, COUNT(*) AS hits
                FROM keyword_index
                WHERE session_id=? AND token IN ({placeholders})
                GROUP BY message_id
                ORDER BY hits DESC
                LIMIT ?
                """,
                (self.session_id, *tokens, limit),
            ).fetchall()
        denom = max(1, len(tokens))
        return [(r["message_id"], float(r["hits"]) / denom) for r in rows]

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM keyword_index WHERE session_id=?", (self.session_id,))
            conn.commit()
