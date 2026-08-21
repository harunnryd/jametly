from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from jamly.agent.ask import (
    AskState,
    Citation,
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_UTTERANCES,
    build_context,
    build_prompt,
)
from jamly.db import LocalStore
from jamly.llm import ChatMessage


def _seed_meeting(store: LocalStore) -> str:
    meeting_id = str(uuid.uuid4())
    store.create_meeting(meeting_id)
    return meeting_id


def _append(store: LocalStore, meeting_id: str, text: str, start_ms: int) -> str:
    return store.append_utterance(
        meeting_id=meeting_id,
        speaker="A",
        text=text,
        start_ms=start_ms,
        end_ms=start_ms + max(1, len(text) // 4),
        confidence=0.9,
        segment_id=str(uuid.uuid4()),
    )


def test_citation_model_validates_and_round_trips() -> None:
    citation = Citation(
        utterance_id="u-1",
        speaker="A",
        start_ms=100,
        text_preview="we agreed on X",
    )
    assert citation.utterance_id == "u-1"
    assert citation.start_ms == 100
    restored = Citation.model_validate_json(citation.model_dump_json())
    assert restored == citation


def test_ask_state_round_trips_through_json() -> None:
    state = AskState(
        thread_id="ask-1",
        meeting_id="m1",
        question="what was decided?",
        answer="we picked X",
        context_utterance_ids=["u-1", "u-2"],
    )
    blob = state.model_dump_json()
    restored = AskState.model_validate_json(blob)
    assert restored == state


def test_build_context_empty_meeting_returns_empty(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed_meeting(store)
        assert build_context(store, meeting_id) == []
    finally:
        store.close()


def test_build_context_preserves_all_utterances_under_budget(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed_meeting(store)
        ids = [
            _append(store, meeting_id, f"u{i}", start_ms=i * 1000)
            for i in range(5)
        ]
        assert [u["id"] for u in build_context(store, meeting_id)] == ids
    finally:
        store.close()


def test_build_context_truncates_to_max_utterances(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed_meeting(store)
        for i in range(MAX_CONTEXT_UTTERANCES + 5):
            _append(store, meeting_id, f"u{i}", start_ms=i * 1000)
        context = build_context(store, meeting_id)
        assert len(context) == MAX_CONTEXT_UTTERANCES
        assert context[-1]["text"] == f"u{MAX_CONTEXT_UTTERANCES + 5 - 1}"
        assert context[0]["text"] == "u5"
    finally:
        store.close()


def test_build_context_truncates_by_char_budget_in_reverse(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed_meeting(store)
        _append(store, meeting_id, "x" * 4000, start_ms=0)
        _append(store, meeting_id, "y" * 4000, start_ms=200)
        _append(store, meeting_id, "z" * 4000, start_ms=400)
        context = build_context(store, meeting_id, max_chars=MAX_CONTEXT_CHARS)
        assert [u["text"] for u in context] == ["y" * 4000, "z" * 4000]
    finally:
        store.close()


def test_build_context_keeps_oversized_single_utterance(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed_meeting(store)
        _append(store, meeting_id, "x" * (MAX_CONTEXT_CHARS * 2), start_ms=0)
        context = build_context(store, meeting_id)
        assert len(context) == 1
        assert context[0]["text"] == "x" * (MAX_CONTEXT_CHARS * 2)
    finally:
        store.close()


def test_build_context_rejects_unknown_meeting(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        with pytest.raises(Exception):
            build_context(store, "missing-meeting")
    finally:
        store.close()


def test_build_prompt_with_context_includes_all_utterances() -> None:
    state = AskState(thread_id="ask-1", meeting_id="m1", question="what was decided?")
    utterances = [
        {"speaker": "A", "text": "let's decide on X", "start_ms": 0, "end_ms": 100},
        {"speaker": "B", "text": "agreed", "start_ms": 200, "end_ms": 300},
    ]
    messages = build_prompt(state, utterances)
    assert len(messages) == 3
    assert messages[0].role == "system"
    assert messages[1].role == "system"
    assert messages[2].role == "user"
    assert messages[2].content == "what was decided?"
    assert "let's decide on X" in messages[1].content
    assert "agreed" in messages[1].content


def test_build_prompt_with_empty_context_drops_context_block() -> None:
    state = AskState(thread_id="ask-1", meeting_id="m1", question="ping?")
    messages = build_prompt(state, [])
    assert [m.role for m in messages] == ["system", "user"]
    assert messages[-1].content == "ping?"


def test_build_prompt_with_overflowing_context_flags_truncation() -> None:
    state = AskState(thread_id="ask-1", meeting_id="m1", question="q")
    utterances = [
        {"speaker": "A", "text": "only line", "start_ms": 0, "end_ms": 100},
    ]
    messages = build_prompt(state, utterances, truncated=True)
    joined = "\n".join(m.content for m in messages)
    assert "truncated" in joined.lower()


def test_chat_message_serialization_matches_frozen_pydantic() -> None:
    message = ChatMessage(role="user", content="hello")
    restored = ChatMessage.model_validate_json(message.model_dump_json())
    assert restored == message
