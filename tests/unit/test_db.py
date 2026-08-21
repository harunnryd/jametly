from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jamly.db import LocalStore, StoreError


def test_fresh_store_migrates_and_round_trips_records(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    meeting_id = store.create_meeting("meeting-1", title="Planning")

    utterance_id = store.append_utterance(meeting_id, "A", "Ship it", 0, 500, 0.9, segment_id="seg-1")
    message_id = store.append_message(meeting_id, "assistant", "I agree")
    action_id = store.append_action_item(meeting_id, "Ship it", owner="A")

    assert meeting_id == "meeting-1"
    assert store.get_meeting(meeting_id)["title"] == "Planning"
    assert store.get_utterance(utterance_id)["text"] == "Ship it"
    assert store.get_utterance(utterance_id)["segment_id"] == "seg-1"
    assert store.get_message(message_id)["content"] == "I agree"
    assert store.get_action_item(action_id)["body"] == "Ship it"
    assert store.schema_version() == 2


def test_search_is_fts_backed_and_bounded(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    meeting_id = store.create_meeting("meeting-1")
    store.append_utterance(meeting_id, "A", "approve the launch", 0, 100, 1.0, segment_id="seg-1")
    store.append_utterance(meeting_id, "B", "review the budget", 100, 200, 1.0, segment_id="seg-2")

    results = store.search("launch", limit=1)

    assert len(results) == 1
    assert results[0]["text"] == "approve the launch"
    assert store.search("", limit=10) == []


def test_transaction_rolls_back_partial_write(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    meeting_id = store.create_meeting("meeting-1")

    with pytest.raises(StoreError):
        with store.transaction():
            store.append_utterance(meeting_id, "A", "temporary", 0, 100, 1.0, segment_id="seg-1")
            raise StoreError("abort")

    assert store.search("temporary") == []


def test_search_rejects_unsafe_fts_query(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    with pytest.raises(StoreError):
        store.search('"', limit=10)


def test_store_rejects_missing_parent_records(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    with pytest.raises(StoreError):
        store.append_utterance("missing", "A", "text", 0, 1, 1.0, segment_id="seg-1")


def test_store_rejects_an_empty_segment_id(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    meeting_id = store.create_meeting("meeting-1")
    with pytest.raises(StoreError):
        store.append_utterance(meeting_id, "A", "text", 0, 1, 1.0, segment_id="")


def test_schema_v2_migrates_an_existing_v1_database(tmp_path: Path) -> None:
    raw = sqlite3.connect(tmp_path / "meeting.sqlite")
    raw.execute("PRAGMA foreign_keys = ON")
    raw.executescript(
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
        PRAGMA user_version = 1;
        """
    )
    raw.commit()
    raw.close()

    store = LocalStore(tmp_path / "meeting.sqlite")
    assert store.schema_version() == 2
    meeting_id = store.create_meeting("meeting-1")
    identifier = store.append_utterance(meeting_id, "A", "legacy", 0, 1, 1.0, segment_id="seg-1")
    assert store.get_utterance(identifier)["segment_id"] == "seg-1"


def test_schema_does_not_create_telemetry_tables(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    tables = {
        row[0]
        for row in store.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert "telemetry" not in tables
    assert "meetings" in tables
    assert "utterances_fts" in tables
