from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from jamly.db import LocalStore
from jamly.meetings.session import (
    CheckpointPayload,
    handle_meeting_get,
    handle_meeting_list,
    handle_meeting_start,
    handle_meeting_stop,
    recover_orphans,
)
from jamly.protocol import ErrorCode, Event, Request


class EventRecorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    async def __call__(self, event: Event) -> None:
        self.events.append(event)

    def meeting_ended(self) -> list[Event]:
        return [event for event in self.events if event.method == "meeting.ended"]

    def reset(self) -> None:
        self.events.clear()


def _store(tmp_path: Path) -> LocalStore:
    return LocalStore(tmp_path / "meeting.sqlite")


async def test_meeting_start_creates_a_durable_meeting_id(tmp_path: Path) -> None:
    store = _store(tmp_path)
    emit = EventRecorder()

    reply = await handle_meeting_start(
        Request(id="r1", method="meeting.start", params={"title": "Planning"}),
        emit,
        store=store,
    )

    assert reply.error is None
    assert isinstance(reply.result, dict)
    meeting_id = reply.result["meeting_id"]
    assert meeting_id
    assert store.get_meeting(meeting_id)["title"] == "Planning"
    assert emit.events == []


async def test_meeting_start_rejects_a_duplicate_active_session(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = await handle_meeting_start(
        Request(id="r1", method="meeting.start", params={}), emit=EventRecorder(), store=store
    )
    assert first.error is None

    second = await handle_meeting_start(
        Request(id="r2", method="meeting.start", params={}), emit=EventRecorder(), store=store
    )

    assert second.error is not None
    assert second.error.code == ErrorCode.INVALID_REQUEST
    assert second.result is None


async def test_meeting_start_rejects_an_invalid_title_type(tmp_path: Path) -> None:
    store = _store(tmp_path)

    reply = await handle_meeting_start(
        Request(id="r1", method="meeting.start", params={"title": 123}),
        emit=EventRecorder(),
        store=store,
    )

    assert reply.error is not None
    assert reply.error.code == ErrorCode.INVALID_REQUEST


async def test_meeting_stop_emits_meeting_ended_exactly_once(tmp_path: Path) -> None:
    store = _store(tmp_path)
    started = await handle_meeting_start(
        Request(id="r1", method="meeting.start", params={}), emit=EventRecorder(), store=store
    )
    meeting_id = started.result["meeting_id"]
    emit = EventRecorder()

    reply = await handle_meeting_stop(
        Request(id="r2", method="meeting.stop", params={"meeting_id": meeting_id}),
        emit,
        store=store,
    )

    assert reply.error is None
    assert reply.result == {"already_ended": False}
    assert len(emit.meeting_ended()) == 1
    ended = emit.meeting_ended()[0]
    assert ended.params["meeting_id"] == meeting_id


async def test_meeting_stop_is_idempotent_and_does_not_re_emit(tmp_path: Path) -> None:
    store = _store(tmp_path)
    started = await handle_meeting_start(
        Request(id="r1", method="meeting.start", params={}), emit=EventRecorder(), store=store
    )
    meeting_id = started.result["meeting_id"]
    first_emit = EventRecorder()
    second_emit = EventRecorder()

    first = await handle_meeting_stop(
        Request(id="r2", method="meeting.stop", params={"meeting_id": meeting_id}),
        first_emit,
        store=store,
    )
    second = await handle_meeting_stop(
        Request(id="r3", method="meeting.stop", params={"meeting_id": meeting_id}),
        second_emit,
        store=store,
    )

    assert first.error is None
    assert first.result == {"already_ended": False}
    assert second.error is None
    assert second.result == {"already_ended": True}
    assert len(first_emit.meeting_ended()) == 1
    assert second_emit.meeting_ended() == []


async def test_meeting_stop_rejects_an_unknown_meeting_id(tmp_path: Path) -> None:
    store = _store(tmp_path)

    reply = await handle_meeting_stop(
        Request(id="r1", method="meeting.stop", params={"meeting_id": "missing"}),
        EventRecorder(),
        store=store,
    )

    assert reply.error is not None
    assert reply.error.code == ErrorCode.MEETING_NOT_FOUND


async def test_meeting_stop_rejects_a_missing_meeting_id_param(tmp_path: Path) -> None:
    store = _store(tmp_path)

    reply = await handle_meeting_stop(
        Request(id="r1", method="meeting.stop", params={}),
        EventRecorder(),
        store=store,
    )

    assert reply.error is not None
    assert reply.error.code == ErrorCode.INVALID_REQUEST


async def test_meeting_list_returns_bounded_recent_meetings(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for index in range(5):
        store.create_meeting(f"meeting-{index}")

    reply = await handle_meeting_list(
        Request(id="r1", method="meeting.list", params={"limit": 3}),
        EventRecorder(),
        store=store,
    )

    assert reply.error is None
    assert isinstance(reply.result, dict)
    assert reply.result["limit"] == 3
    assert len(reply.result["meetings"]) == 3


async def test_meeting_list_search_filters_via_utterance_text(tmp_path: Path) -> None:
    store = _store(tmp_path)
    target = store.create_meeting("target")
    other = store.create_meeting("other")
    store.append_utterance(target, "A", "approve the launch", 0, 100, 1.0, segment_id="seg-1")
    store.append_utterance(other, "A", "review the budget", 100, 200, 1.0, segment_id="seg-2")

    reply = await handle_meeting_list(
        Request(id="r1", method="meeting.list", params={"search": "launch"}),
        EventRecorder(),
        store=store,
    )

    assert reply.error is None
    assert [m["id"] for m in reply.result["meetings"]] == [target]


async def test_meeting_get_returns_meeting_and_utterances(tmp_path: Path) -> None:
    store = _store(tmp_path)
    meeting_id = store.create_meeting("meeting-1", title="Planning")
    store.append_utterance(meeting_id, "A", "Ship it", 0, 500, 0.9, segment_id="seg-1")

    reply = await handle_meeting_get(
        Request(id="r1", method="meeting.get", params={"meeting_id": meeting_id}),
        EventRecorder(),
        store=store,
    )

    assert reply.error is None
    payload = reply.result
    assert payload["meeting"]["id"] == meeting_id
    assert payload["meeting"]["title"] == "Planning"
    assert len(payload["utterances"]) == 1


async def test_meeting_get_unknown_id_returns_meeting_not_found(tmp_path: Path) -> None:
    store = _store(tmp_path)

    reply = await handle_meeting_get(
        Request(id="r1", method="meeting.get", params={"meeting_id": "missing"}),
        EventRecorder(),
        store=store,
    )

    assert reply.error is not None
    assert reply.error.code == ErrorCode.MEETING_NOT_FOUND


async def test_recover_orphans_writes_a_checkpoint_and_does_not_close_the_meeting(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    orphan = store.create_meeting("orphan-1")
    closed = store.create_meeting("closed-1")
    store.end_meeting(closed)
    emit = EventRecorder()

    await recover_orphans(store, emit)

    assert store.get_meeting(orphan)["ended_at"] is None
    assert store.load_checkpoint(orphan, CheckpointPayload).status == "recovered_on_cold_start"
    assert emit.meeting_ended() == []


async def test_recover_orphans_does_nothing_when_no_meetings_exist(tmp_path: Path) -> None:
    store = _store(tmp_path)
    emit = EventRecorder()

    await recover_orphans(store, emit)

    assert emit.events == []


async def test_recover_orphans_does_not_close_a_session_whose_meeting_stop_already_won(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    started = await handle_meeting_start(
        Request(id="r1", method="meeting.start", params={}), emit=EventRecorder(), store=store
    )
    meeting_id = started.result["meeting_id"]
    await handle_meeting_stop(
        Request(id="r2", method="meeting.stop", params={"meeting_id": meeting_id}),
        EventRecorder(),
        store=store,
    )
    emit = EventRecorder()

    await recover_orphans(store, emit)

    assert store.get_meeting(meeting_id)["ended_at"] is not None
    assert emit.meeting_ended() == []
