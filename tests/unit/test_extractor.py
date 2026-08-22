from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from jamly.db import LocalStore
from jamly.meetings.extractor import (
    FOLLOWUP_EMIT,
    FOLLOWUP_KINDS,
    UNKNOWN_SOURCE,
    ActionItem,
    ActionItems,
    FollowUp,
    FollowUps,
    build_transcript,
    evidence_enum,
    followup_event,
    followups_schema,
    format_transcript,
    ground_items,
    stamp_followups,
    structured_call,
    utterance_start_ms,
    valid_utterance_ids,
)


class FakeStructured:
    def __init__(self, outcomes: list[dict[str, Any]]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[list[Any]] = []

    async def ainvoke(self, messages: list[Any]) -> dict[str, Any]:
        self.calls.append(list(messages))
        if not self._outcomes:
            raise AssertionError("structured runnable invoked more times than planned")
        return self._outcomes.pop(0)


def _ok(parsed: dict[str, Any]) -> dict[str, Any]:
    return {"raw": "raw-text", "parsed": parsed, "parsing_error": None}


def _bad(error: str) -> dict[str, Any]:
    return {"raw": "raw-text", "parsed": None, "parsing_error": ValueError(error)}


def _seed(store: LocalStore, texts: tuple[str, ...]) -> tuple[str, list[str]]:
    meeting_id = store.create_meeting(title="standup")
    ids: list[str] = []
    for index, text in enumerate(texts):
        ids.append(
            store.append_utterance(
                meeting_id=meeting_id,
                speaker="A",
                text=text,
                start_ms=index * 1000,
                end_ms=index * 1000 + 500,
                confidence=0.9,
                segment_id=str(uuid.uuid4()),
            )
        )
    return meeting_id, ids


def test_action_item_requires_at_least_one_source_id() -> None:
    with pytest.raises(ValidationError):
        ActionItem(body="ship the thing", source_utterance_ids=[])


def test_action_item_accepts_the_unknown_source_marker() -> None:
    item = ActionItem(body="ship the thing", source_utterance_ids=[UNKNOWN_SOURCE])
    assert item.source_utterance_ids == [UNKNOWN_SOURCE]
    assert item.owner == ""


def test_unknown_source_marker_cannot_be_mixed_with_real_ids() -> None:
    with pytest.raises(ValidationError):
        ActionItem(body="ship the thing", source_utterance_ids=[UNKNOWN_SOURCE, "u-1"])


def test_followup_kinds_cover_question_contradiction_action_and_todo() -> None:
    assert FOLLOWUP_KINDS == ("question", "contradiction", "action", "todo")
    for kind in FOLLOWUP_KINDS:
        followup = FollowUp(kind=kind, body="something", source_utterance_ids=["u-1"])
        assert followup.kind == kind


def test_followup_rejects_an_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        FollowUp(kind="rumour", body="something", source_utterance_ids=["u-1"])


def test_followup_event_carries_kind_body_ts_and_citations() -> None:
    followup = FollowUp(
        kind="action", body="email the client", ts_ms=4200, source_utterance_ids=["u-7"]
    )
    event = followup_event(followup, meeting_id="m-1")

    assert event.method == FOLLOWUP_EMIT
    assert event.params["meeting_id"] == "m-1"
    assert event.params["kind"] == "action"
    assert event.params["body"] == "email the client"
    assert event.params["ts_ms"] == 4200
    assert event.params["citations"] == ["u-7"]


def test_ground_items_keeps_supported_items_and_drops_hallucinated_ids() -> None:
    kept, dropped = ground_items(
        [
            ActionItem(body="real one", source_utterance_ids=["u-1"]),
            ActionItem(body="invented", source_utterance_ids=["u-999"]),
        ],
        {"u-1", "u-2"},
    )

    assert [item.body for item in kept] == ["real one"]
    assert len(dropped) == 1
    assert "u-999" in dropped[0]
    assert "invented" in dropped[0]


def test_ground_items_drops_unknown_source_items_as_unsupported() -> None:
    kept, dropped = ground_items(
        [ActionItem(body="no evidence", source_utterance_ids=[UNKNOWN_SOURCE])],
        {"u-1"},
    )

    assert kept == []
    assert len(dropped) == 1
    assert UNKNOWN_SOURCE in dropped[0]


def test_ground_items_on_an_empty_id_set_drops_everything() -> None:
    kept, dropped = ground_items(
        [ActionItem(body="x y z", source_utterance_ids=["u-1"])], set()
    )

    assert kept == []
    assert len(dropped) == 1


def test_evidence_enum_offers_valid_ids_plus_the_unknown_marker() -> None:
    assert evidence_enum(["u-2", "u-1"]) == ["u-1", "u-2", UNKNOWN_SOURCE]


def test_evidence_enum_falls_back_to_the_marker_alone_when_there_are_no_ids() -> None:
    assert evidence_enum([]) == [UNKNOWN_SOURCE]


def test_valid_utterance_ids_and_start_ms_index_the_transcript(tmp_path: Any) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id, ids = _seed(store, ("alpha", "beta"))
        transcript = build_transcript(store, meeting_id)

        assert valid_utterance_ids(transcript) == set(ids)
        assert utterance_start_ms(transcript) == {ids[0]: 0, ids[1]: 1000}
    finally:
        store.close()


def test_build_transcript_returns_the_full_meeting_oldest_first(tmp_path: Any) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id, ids = _seed(store, ("first", "second", "third"))
        transcript = build_transcript(store, meeting_id)

        assert [row["id"] for row in transcript] == ids
        assert [row["text"] for row in transcript] == ["first", "second", "third"]
    finally:
        store.close()


def test_build_transcript_keeps_the_newest_utterances_under_the_char_budget(
    tmp_path: Any,
) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id, ids = _seed(store, ("a" * 40, "b" * 40, "c" * 40))
        transcript = build_transcript(store, meeting_id, max_chars=90)

        assert [row["id"] for row in transcript] == ids[1:]
    finally:
        store.close()


def test_build_transcript_of_a_meeting_with_no_utterances_is_empty(
    tmp_path: Any,
) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = store.create_meeting(title="silent")
        assert build_transcript(store, meeting_id) == []
    finally:
        store.close()


def test_format_transcript_tags_every_line_with_its_utterance_id() -> None:
    block = format_transcript(
        [
            {"id": "u-1", "speaker": "A", "start_ms": 0, "text": "hello"},
            {"id": "u-2", "speaker": "B", "start_ms": 1000, "text": "world"},
        ]
    )

    assert "[u-1]" in block
    assert "[u-2]" in block
    assert "hello" in block
    assert "world" in block


async def test_structured_call_returns_the_parsed_object_on_first_success() -> None:
    structured = FakeStructured([_ok({"items": []})])

    parsed, failures = await structured_call(structured, ["prompt"])

    assert parsed == {"items": []}
    assert failures == []
    assert len(structured.calls) == 1


async def test_structured_call_repairs_malformed_model_output_on_a_second_attempt() -> (
    None
):
    structured = FakeStructured([_bad("items: field required"), _ok({"items": []})])

    parsed, failures = await structured_call(structured, ["prompt"])

    assert parsed == {"items": []}
    assert len(failures) == 1
    assert "items: field required" in failures[0]
    assert len(structured.calls) == 2
    assert len(structured.calls[1]) > len(structured.calls[0])


async def test_structured_call_gives_up_after_the_attempt_budget() -> None:
    structured = FakeStructured([_bad("nope-1"), _bad("nope-2")])

    parsed, failures = await structured_call(structured, ["prompt"], max_attempts=2)

    assert parsed is None
    assert len(failures) == 2
    assert len(structured.calls) == 2


async def test_structured_call_treats_a_missing_parsed_object_as_a_failure() -> None:
    structured = FakeStructured(
        [{"raw": "junk", "parsed": None, "parsing_error": None}]
    )

    parsed, failures = await structured_call(structured, ["prompt"], max_attempts=1)

    assert parsed is None
    assert len(failures) == 1


def test_action_items_and_followups_containers_default_to_empty() -> None:
    assert ActionItems().items == []
    assert FollowUps().items == []


def test_followups_schema_offers_only_the_four_kinds_and_grounded_evidence() -> None:
    schema = followups_schema(["u-1"])
    item = schema["properties"]["items"]["items"]["properties"]

    assert item["kind"]["enum"] == list(FOLLOWUP_KINDS)
    assert item["source_utterance_ids"]["items"]["enum"] == ["u-1", UNKNOWN_SOURCE]
    assert "ts_ms" not in item


def test_stamp_followups_takes_the_timestamp_from_the_earliest_cited_utterance() -> (
    None
):
    stamped = stamp_followups(
        [
            FollowUp(
                kind="todo", body="write the doc", source_utterance_ids=["u-2", "u-1"]
            ),
            FollowUp(kind="question", body="who owns it", source_utterance_ids=["u-3"]),
        ],
        {"u-1": 1000, "u-2": 5000},
    )

    assert stamped[0].ts_ms == 1000
    assert stamped[1].ts_ms == 0
