from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from jamly.db import LocalStore, StoreError


class CheckpointPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    segment_id: str = ""


def test_end_meeting_returns_true_only_on_the_first_closure(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    meeting_id = store.create_meeting("meeting-1")

    assert store.end_meeting(meeting_id) is True
    assert store.end_meeting(meeting_id) is False


def test_end_meeting_records_a_non_null_ended_at(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    meeting_id = store.create_meeting("meeting-1")

    store.end_meeting(meeting_id)

    row = store.get_meeting(meeting_id)
    assert row["ended_at"] is not None
    assert row["ended_at"] != ""


def test_end_meeting_unknown_id_raises_store_error(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")

    with pytest.raises(StoreError):
        store.end_meeting("does-not-exist")


def test_get_active_meeting_returns_none_when_no_session_is_open(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")

    assert store.get_active_meeting() is None


def test_get_active_meeting_returns_the_one_open_session(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    store.create_meeting("open-meeting")
    store.create_meeting("closed-meeting")
    store.end_meeting("closed-meeting")

    active = store.get_active_meeting()

    assert active is not None
    assert active["id"] == "open-meeting"


def test_get_full_meeting_returns_meeting_and_ordered_utterances(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    meeting_id = store.create_meeting("meeting-1", title="Planning")
    store.append_utterance(meeting_id, "A", "second", 200, 400, 0.9, segment_id="seg-2")
    store.append_utterance(meeting_id, "B", "first", 0, 100, 0.8, segment_id="seg-1")
    store.append_utterance(meeting_id, "A", "third", 500, 600, 0.7, segment_id="seg-3")

    payload = store.get_full_meeting(meeting_id)

    assert payload["meeting"]["id"] == meeting_id
    assert payload["meeting"]["title"] == "Planning"
    assert [u["text"] for u in payload["utterances"]] == ["first", "second", "third"]


def test_get_full_meeting_unknown_id_raises_store_error(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")

    with pytest.raises(StoreError):
        store.get_full_meeting("does-not-exist")


def test_list_meetings_returns_bounded_results_newest_first(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    for index in range(5):
        store.create_meeting(f"meeting-{index}")

    payload = store.list_meetings(limit=3)

    assert payload["limit"] == 3
    assert len(payload["meetings"]) == 3


def test_list_meetings_with_search_filters_via_utterance_text(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    target = store.create_meeting("target")
    other = store.create_meeting("other")
    store.append_utterance(target, "A", "approve the launch", 0, 100, 1.0, segment_id="seg-1")
    store.append_utterance(other, "A", "review the budget", 100, 200, 1.0, segment_id="seg-2")

    payload = store.list_meetings(search="launch", limit=20)

    assert len(payload["meetings"]) == 1
    assert payload["meetings"][0]["id"] == target


def test_list_meetings_search_rejects_an_empty_query(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    store.create_meeting("meeting-1")

    payload = store.list_meetings(search="   ", limit=20)

    assert payload["meetings"] == []


def test_save_and_load_checkpoint_round_trip_a_pydantic_payload(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    meeting_id = store.create_meeting("meeting-1")
    payload = CheckpointPayload(status="recovered_on_cold_start", segment_id="seg-9")

    store.save_checkpoint(meeting_id, payload)
    loaded = store.load_checkpoint(meeting_id, CheckpointPayload)

    assert loaded == payload


def test_save_checkpoint_overwrites_a_prior_payload(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    meeting_id = store.create_meeting("meeting-1")

    store.save_checkpoint(meeting_id, CheckpointPayload(status="first"))
    store.save_checkpoint(meeting_id, CheckpointPayload(status="second"))

    assert store.load_checkpoint(meeting_id, CheckpointPayload).status == "second"


def test_load_checkpoint_unknown_meeting_raises_store_error(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")

    with pytest.raises(StoreError):
        store.load_checkpoint("does-not-exist", CheckpointPayload)


def test_save_checkpoint_requires_an_existing_meeting(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")

    with pytest.raises(StoreError):
        store.save_checkpoint("does-not-exist", CheckpointPayload(status="x"))


def test_find_orphans_returns_only_meetings_with_null_ended_at(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    store.create_meeting("open-1")
    closed = store.create_meeting("closed-1")
    store.end_meeting(closed)
    store.create_meeting("open-2")

    orphans = store.find_orphans()

    assert sorted(orphan["id"] for orphan in orphans) == ["open-1", "open-2"]


def test_find_orphans_is_empty_when_all_meetings_are_closed(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "meeting.sqlite")
    meeting_id = store.create_meeting("meeting-1")
    store.end_meeting(meeting_id)

    assert store.find_orphans() == []
