"""Append-only SQLite message store, scoped to one session_id."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.context.errors import ContextSecurityError
from src.context.runtime.conversation_context import Message, MessageRole


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


class MessageStore:
    def __init__(self, db_path: Path, session_id: str) -> None:
        self.session_id = session_id
        self.db_path = db_path
        self._lock = threading.Lock()
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
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    token_count INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at)"
            )
            conn.commit()

    def append(self, message: Message) -> Message:
        msg_id = message.id or str(uuid.uuid4())
        created_at = message.created_at or _now_iso()
        stored = Message(
            role=message.role,
            content=message.content,
            created_at=created_at,
            id=msg_id,
            metadata=dict(message.metadata),
        )
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO messages
                    (id, session_id, role, content, created_at, metadata_json, token_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stored.id,
                        self.session_id,
                        stored.role,
                        stored.content,
                        stored.created_at,
                        json.dumps(stored.metadata),
                        _estimate_tokens(stored.content),
                    ),
                )
                conn.commit()
        return stored

    def get_by_id(self, message_id: str) -> Message | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        if row is None:
            return None
        self._assert_session(row["session_id"])
        return self._row_to_message(row)

    def get_recent(
        self, n: int = 20, roles: tuple[MessageRole, ...] | None = None
    ) -> list[Message]:
        with self._connect() as conn:
            if roles:
                placeholders = ",".join("?" * len(roles))
                rows = conn.execute(
                    f"""
                    SELECT * FROM messages
                    WHERE session_id=? AND role IN ({placeholders})
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (self.session_id, *roles, n),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM messages
                    WHERE session_id=?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (self.session_id, n),
                ).fetchall()
        messages = [self._row_to_message(r) for r in rows]
        messages.reverse()  # chronological
        return messages

    def get_all(self) -> list[Message]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM messages WHERE session_id=?
                ORDER BY created_at ASC
                """,
                (self.session_id,),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def get_after(self, message_id: str | None) -> list[Message]:
        all_msgs = self.get_all()
        if message_id is None:
            return all_msgs
        for i, m in enumerate(all_msgs):
            if m.id == message_id:
                return all_msgs[i + 1 :]
        return all_msgs

    def unsummarized_token_count(self, covers_through_id: str | None) -> int:
        msgs = self.get_after(covers_through_id)
        return sum(_estimate_tokens(m.content) for m in msgs)

    def total_token_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(token_count), 0) AS t FROM messages WHERE session_id=?",
                (self.session_id,),
            ).fetchone()
        return int(row["t"])

    def clear(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM messages WHERE session_id=?", (self.session_id,))
                conn.commit()

    def _assert_session(self, row_session_id: str) -> None:
        if row_session_id != self.session_id:
            raise ContextSecurityError(
                f"session boundary violation: expected {self.session_id!r}, got {row_session_id!r}"
            )

    def _row_to_message(self, row: sqlite3.Row) -> Message:
        self._assert_session(row["session_id"])
        return Message(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )
