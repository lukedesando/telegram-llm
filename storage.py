from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StoredMessage:
    id: int
    role: str
    content: str


class SQLiteConversationStore:
    """Durable raw conversation history plus rolling-summary metadata."""

    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.database_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL DEFAULT '',
                    summary_through_message_id INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
                ON messages(conversation_id, id);
                """
            )

    def append_message(self, conversation_id: str, role: str, content: str) -> int:
        if role not in {"user", "assistant"}:
            raise ValueError(f"unsupported role: {role}")
        with self._connection() as conn:
            conn.execute("INSERT OR IGNORE INTO conversations(id) VALUES (?)", (conversation_id,))
            cursor = conn.execute(
                "INSERT INTO messages(conversation_id, role, content) VALUES (?, ?, ?)",
                (conversation_id, role, content),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (conversation_id,),
            )
            return int(cursor.lastrowid)

    def state(self, conversation_id: str) -> tuple[str, int]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT summary, summary_through_message_id FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return "", 0
        return str(row["summary"]), int(row["summary_through_message_id"])

    def messages_after(self, conversation_id: str, after_message_id: int = 0) -> list[StoredMessage]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content
                FROM messages
                WHERE conversation_id = ? AND id > ?
                ORDER BY id ASC
                """,
                (conversation_id, after_message_id),
            ).fetchall()
        return [StoredMessage(int(r["id"]), str(r["role"]), str(r["content"])) for r in rows]

    def recent_messages(
        self,
        conversation_id: str,
        after_message_id: int,
        limit: int,
    ) -> list[StoredMessage]:
        if limit <= 0:
            return []
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content
                FROM messages
                WHERE conversation_id = ? AND id > ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, after_message_id, limit),
            ).fetchall()
        rows = list(reversed(rows))
        return [StoredMessage(int(r["id"]), str(r["role"]), str(r["content"])) for r in rows]

    def all_messages(self, conversation_id: str) -> list[StoredMessage]:
        return self.messages_after(conversation_id, 0)

    def set_summary(self, conversation_id: str, summary: str, through_message_id: int) -> None:
        with self._connection() as conn:
            conn.execute("INSERT OR IGNORE INTO conversations(id) VALUES (?)", (conversation_id,))
            conn.execute(
                """
                UPDATE conversations
                SET summary = ?, summary_through_message_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (summary, through_message_id, conversation_id),
            )

    def clear(self, conversation_id: str) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
