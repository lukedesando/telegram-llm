from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StoredMessage:
    id: int
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ConversationStats:
    message_count: int
    summary_present: bool
    pending_message_count: int


class SQLiteConversationStore:
    """Durable conversation state plus Telegram delivery bookkeeping."""

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

                CREATE TABLE IF NOT EXISTS telegram_updates (
                    update_id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL CHECK (status IN ('processing', 'completed')),
                    updated_at REAL NOT NULL
                );
                """
            )

    def ping(self) -> bool:
        try:
            with self._connection() as conn:
                row = conn.execute("SELECT 1 AS ok").fetchone()
            return row is not None and int(row["ok"]) == 1
        except sqlite3.Error:
            return False

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

    def conversation_stats(self, conversation_id: str) -> ConversationStats:
        with self._connection() as conn:
            conversation = conn.execute(
                "SELECT summary, summary_through_message_id FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if conversation is None:
                return ConversationStats(0, False, 0)
            through_id = int(conversation["summary_through_message_id"])
            counts = conn.execute(
                """
                SELECT
                    COUNT(*) AS message_count,
                    SUM(CASE WHEN id > ? THEN 1 ELSE 0 END) AS pending_count
                FROM messages
                WHERE conversation_id = ?
                """,
                (through_id, conversation_id),
            ).fetchone()
        return ConversationStats(
            int(counts["message_count"] or 0),
            bool(str(conversation["summary"]).strip()),
            int(counts["pending_count"] or 0),
        )

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

    def claim_update(self, update_id: int, stale_after_seconds: int = 300) -> bool:
        """Claim a Telegram update once, allowing abandoned processing leases to expire."""
        if stale_after_seconds < 0:
            raise ValueError("stale_after_seconds must be non-negative")
        now = time.time()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status, updated_at FROM telegram_updates WHERE update_id = ?",
                (update_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO telegram_updates(update_id, status, updated_at) VALUES (?, 'processing', ?)",
                    (update_id, now),
                )
                return True
            if row["status"] == "completed":
                return False
            if now - float(row["updated_at"]) < stale_after_seconds:
                return False
            conn.execute(
                "UPDATE telegram_updates SET status = 'processing', updated_at = ? WHERE update_id = ?",
                (now, update_id),
            )
            return True

    def complete_update(self, update_id: int) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE telegram_updates
                SET status = 'completed', updated_at = ?
                WHERE update_id = ?
                """,
                (time.time(), update_id),
            )

    def release_update(self, update_id: int) -> None:
        with self._connection() as conn:
            conn.execute(
                "DELETE FROM telegram_updates WHERE update_id = ? AND status = 'processing'",
                (update_id,),
            )
