from __future__ import annotations

import uuid
from pathlib import Path

from pydantic import ValidationError

from jamly.agent.ask import AskState
from jamly.agent.checkpoint import (
    load_ask_state,
    save_ask_state,
)
from jamly.db import LocalStore


def _seed(store: LocalStore) -> str:
    meeting_id = str(uuid.uuid4())
    store.create_meeting(meeting_id)
    return meeting_id


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed(store)
        state = AskState(
            thread_id="ask-1",
            meeting_id=meeting_id,
            question="what was decided?",
            answer="we picked X",
            context_utterance_ids=["u-1", "u-2"],
        )
        save_ask_state(store, state)
        loaded = load_ask_state(store, meeting_id, "ask-1")
        assert loaded == state
    finally:
        store.close()


def test_load_unknown_session_returns_none(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed(store)
        assert load_ask_state(store, meeting_id, "never-saved") is None
    finally:
        store.close()


def test_load_returns_none_after_payload_corruption(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed(store)
        store.connection.execute(
            "INSERT INTO checkpoints(thread_id, payload) VALUES (?, 'not json')",
            (meeting_id,),
        )
        store.connection.commit()
        assert load_ask_state(store, meeting_id, "any") is None
    finally:
        store.close()


def test_two_sessions_in_same_meeting_are_isolated(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed(store)
        state_a = AskState(thread_id="a", meeting_id=meeting_id, question="qa", answer="aa")
        state_b = AskState(thread_id="b", meeting_id=meeting_id, question="qb", answer="bb")
        save_ask_state(store, state_a)
        save_ask_state(store, state_b)
        save_ask_state(
            store,
            AskState(thread_id="a", meeting_id=meeting_id, question="qa2", answer="aa2"),
        )
        assert load_ask_state(store, meeting_id, "a").question == "qa2"
        assert load_ask_state(store, meeting_id, "b").question == "qb"
    finally:
        store.close()


def test_save_rejects_unknown_meeting(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        state = AskState(thread_id="x", meeting_id="missing", question="q")
        try:
            save_ask_state(store, state)
        except Exception as exc:
            assert "not found" in str(exc) or "checkpoint" in str(exc).lower()
        else:
            raise AssertionError("expected an error")
    finally:
        store.close()


def test_invalid_ask_state_does_not_crash_load(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed(store)
        bad = AskState(thread_id="x", meeting_id=meeting_id, question="q")
        bad_blob = bad.model_dump_json().replace("ask-1", "x")
        store.connection.execute(
            "INSERT INTO checkpoints(thread_id, payload) VALUES (?, ?)",
            (meeting_id, bad_blob.replace(bad.thread_id, bad.thread_id)),
        )
        store.connection.commit()
        result = load_ask_state(store, meeting_id, "missing-session")
        assert result is None
    finally:
        store.close()
