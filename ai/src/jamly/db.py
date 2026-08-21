"""Local SQLite store owned by the Python sidecar."""

from __future__ import annotations

import contextlib
import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .config import ConfigPaths


class StoreError(Exception):
    """A safe, user-facing local-store error without SQL or secret values."""


SCHEMA_VERSION = 1


class LocalStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._transaction_depth = 0
        self._migrate()

    @classmethod
    def from_paths(cls, paths: ConfigPaths) -> LocalStore:
        return cls(paths.config_file.with_name("jametly.sqlite"))

    def close(self) -> None:
        self.connection.close()

    def schema_version(self) -> int:
        return int(self.connection.execute("PRAGMA user_version").fetchone()[0])

    def _migrate(self) -> None:
        if self.schema_version() > SCHEMA_VERSION:
            raise StoreError("database version is newer than this application")
        if self.schema_version() == 0:
            self.connection.executescript(
                """
                CREATE TABLE meetings (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    ended_at TEXT
                );
                CREATE TABLE utterances (
                    id TEXT PRIMARY KEY,
                    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                    speaker TEXT NOT NULL,
                    text TEXT NOT NULL,
                    start_ms INTEGER NOT NULL,
                    end_ms INTEGER NOT NULL,
                    confidence REAL NOT NULL
                );
                CREATE VIRTUAL TABLE utterances_fts USING fts5(
                    text,
                    content='utterances',
                    content_rowid='rowid'
                );
                CREATE TRIGGER utterances_ai AFTER INSERT ON utterances BEGIN
                    INSERT INTO utterances_fts(rowid, text) VALUES (new.rowid, new.text);
                END;
                CREATE TRIGGER utterances_ad AFTER DELETE ON utterances BEGIN
                    INSERT INTO utterances_fts(utterances_fts, rowid, text)
                    VALUES ('delete', old.rowid, old.text);
                END;
                CREATE TRIGGER utterances_au AFTER UPDATE OF text ON utterances BEGIN
                    INSERT INTO utterances_fts(utterances_fts, rowid, text)
                    VALUES ('delete', old.rowid, old.text);
                    INSERT INTO utterances_fts(rowid, text) VALUES (new.rowid, new.text);
                END;
                CREATE TABLE messages (
                    id TEXT PRIMARY KEY,
                    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE action_items (
                    id TEXT PRIMARY KEY,
                    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                    body TEXT NOT NULL,
                    owner TEXT,
                    completed INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE checkpoints (
                    thread_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                PRAGMA user_version = 1;
                """
            )
            self.connection.commit()

    @contextlib.contextmanager
    def transaction(self) -> Iterator[None]:
        self._transaction_depth += 1
        try:
            if self._transaction_depth == 1:
                self.connection.execute("BEGIN")
            yield
        except Exception:
            self._transaction_depth = 0
            self.connection.rollback()
            raise
        else:
            self._transaction_depth -= 1
            if self._transaction_depth == 0:
                self.connection.commit()

    def _commit_if_outer_transaction(self) -> None:
        if self._transaction_depth == 0:
            self.connection.commit()

    def create_meeting(self, meeting_id: str | None = None, *, title: str = "") -> str:
        meeting_id = meeting_id or str(uuid.uuid4())
        try:
            self.connection.execute("INSERT INTO meetings(id, title) VALUES (?, ?)", (meeting_id, title))
            self._commit_if_outer_transaction()
        except sqlite3.IntegrityError as error:
            raise StoreError("meeting already exists") from error
        return meeting_id

    def get_meeting(self, meeting_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if row is None:
            raise StoreError("meeting not found")
        return dict(row)

    def _require_meeting(self, meeting_id: str) -> None:
        if self.connection.execute("SELECT 1 FROM meetings WHERE id = ?", (meeting_id,)).fetchone() is None:
            raise StoreError("meeting not found")

    def append_utterance(
        self, meeting_id: str, speaker: str, text: str, start_ms: int, end_ms: int, confidence: float
    ) -> str:
        self._require_meeting(meeting_id)
        if start_ms < 0 or end_ms < start_ms or not 0 <= confidence <= 1:
            raise StoreError("invalid utterance")
        identifier = str(uuid.uuid4())
        self.connection.execute(
            "INSERT INTO utterances(id, meeting_id, speaker, text, start_ms, end_ms, confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (identifier, meeting_id, speaker, text, start_ms, end_ms, confidence),
        )
        self._commit_if_outer_transaction()
        return identifier

    def get_utterance(self, identifier: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM utterances WHERE id = ?", (identifier,)).fetchone()
        if row is None:
            raise StoreError("utterance not found")
        return dict(row)

    def append_message(self, meeting_id: str, role: str, content: str) -> str:
        self._require_meeting(meeting_id)
        identifier = str(uuid.uuid4())
        self.connection.execute(
            "INSERT INTO messages(id, meeting_id, role, content) VALUES (?, ?, ?, ?)",
            (identifier, meeting_id, role, content),
        )
        self._commit_if_outer_transaction()
        return identifier

    def get_message(self, identifier: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM messages WHERE id = ?", (identifier,)).fetchone()
        if row is None:
            raise StoreError("message not found")
        return dict(row)

    def append_action_item(self, meeting_id: str, body: str, *, owner: str | None = None) -> str:
        self._require_meeting(meeting_id)
        identifier = str(uuid.uuid4())
        self.connection.execute(
            "INSERT INTO action_items(id, meeting_id, body, owner) VALUES (?, ?, ?, ?)",
            (identifier, meeting_id, body, owner),
        )
        self._commit_if_outer_transaction()
        return identifier

    def get_action_item(self, identifier: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM action_items WHERE id = ?", (identifier,)).fetchone()
        if row is None:
            raise StoreError("action item not found")
        return dict(row)

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        if '"' in query or "\x00" in query:
            raise StoreError("invalid search query")
        limit = max(1, min(limit, 100))
        rows = self.connection.execute(
            """
            SELECT u.id, u.meeting_id, u.speaker, u.text, u.start_ms, u.end_ms, u.confidence
            FROM utterances_fts f
            JOIN utterances u ON u.rowid = f.rowid
            WHERE utterances_fts MATCH ?
            ORDER BY bm25(utterances_fts), u.start_ms
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [dict(row) for row in rows]
