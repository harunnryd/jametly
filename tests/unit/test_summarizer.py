from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from pydantic import ValidationError

from jamly.agent.chat import ProviderUnavailableError
from jamly.config import AppConfig
from jamly.db import LocalStore
from jamly.meetings.extractor import UNKNOWN_SOURCE, ActionItem
from jamly.meetings.summarizer import (
    SUMMARY_SYSTEM_PROMPT,
    MeetingSummary,
    SummaryPoint,
    build_summary_messages,
    summarize_meeting,
    summary_schema,
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


class FakeStructuredChatModel(BaseChatModel):
    _outcomes: list[dict[str, Any]]
    _raises: BaseException | None
    _schemas: list[Any]
    _structured: FakeStructured | None

    def __init__(
        self,
        outcomes: list[dict[str, Any]] | None = None,
        raises: BaseException | None = None,
    ) -> None:
        super().__init__()
        self._outcomes = list(outcomes or [])
        self._raises = raises
        self._schemas = []
        self._structured = None

    @property
    def _llm_type(self) -> str:
        return "summary-structured-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        raise AssertionError("summarization must use structured output, not _generate")

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        self._schemas.append(schema)
        if self._raises is not None:
            raise self._raises
        self._structured = FakeStructured(self._outcomes)
        return self._structured


def _ok(parsed: dict[str, Any]) -> dict[str, Any]:
    return {"raw": "raw-text", "parsed": parsed, "parsing_error": None}


def _bad(error: str) -> dict[str, Any]:
    return {"raw": "raw-text", "parsed": None, "parsing_error": ValueError(error)}


def _factory(model: BaseChatModel) -> Callable[..., BaseChatModel]:
    def factory(provider_id: str, *, model_name: str) -> BaseChatModel:
        return model

    return factory


def _seed(
    store: LocalStore, texts: tuple[str, ...] = ("we ship friday", "risk is the api")
) -> tuple[str, list[str]]:
    meeting_id = store.create_meeting(title="planning")
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


def test_meeting_summary_exposes_decisions_risks_questions_and_action_items() -> None:
    summary = MeetingSummary(meeting_id="m-1")

    assert summary.decisions == []
    assert summary.risks == []
    assert summary.questions == []
    assert summary.action_items == []


def test_meeting_summary_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MeetingSummary(meeting_id="m-1", notes="freeform")


def test_summary_point_requires_a_source_id_or_the_unknown_marker() -> None:
    with pytest.raises(ValidationError):
        SummaryPoint(body="we ship friday", source_utterance_ids=[])

    point = SummaryPoint(body="we ship friday", source_utterance_ids=[UNKNOWN_SOURCE])
    assert point.source_utterance_ids == [UNKNOWN_SOURCE]


def test_summary_schema_constrains_evidence_to_the_transcript_ids() -> None:
    schema = summary_schema(["u-1", "u-2"])
    properties = schema["properties"]

    assert set(properties) == {"decisions", "risks", "questions", "action_items"}
    for name in ("decisions", "risks", "questions"):
        evidence = properties[name]["items"]["properties"]["source_utterance_ids"]
        assert evidence["items"]["enum"] == ["u-1", "u-2", UNKNOWN_SOURCE]
    actions = properties["action_items"]["items"]["properties"]
    assert actions["source_utterance_ids"]["items"]["enum"] == [
        "u-1",
        "u-2",
        UNKNOWN_SOURCE,
    ]
    assert "owner" in actions


def test_build_summary_messages_carries_the_system_prompt_and_the_transcript() -> None:
    messages = build_summary_messages("[u-1] A@0ms: hello")

    assert len(messages) == 2
    assert SUMMARY_SYSTEM_PROMPT in str(messages[0].content)
    assert "[u-1]" in str(messages[1].content)


async def test_summarize_meeting_returns_grounded_typed_fields(tmp_path: Any) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id, ids = _seed(store)
        model = FakeStructuredChatModel(
            [
                _ok(
                    {
                        "decisions": [
                            {"body": "ship on friday", "source_utterance_ids": [ids[0]]}
                        ],
                        "risks": [
                            {"body": "api may slip", "source_utterance_ids": [ids[1]]}
                        ],
                        "questions": [],
                        "action_items": [
                            {
                                "body": "confirm the api",
                                "owner": "A",
                                "source_utterance_ids": [ids[1]],
                            }
                        ],
                    }
                )
            ]
        )

        outcome = await summarize_meeting(
            store, meeting_id, model_factory=_factory(model), config=AppConfig()
        )

        assert outcome.summary.meeting_id == meeting_id
        assert [point.body for point in outcome.summary.decisions] == ["ship on friday"]
        assert [point.body for point in outcome.summary.risks] == ["api may slip"]
        assert outcome.summary.questions == []
        assert [item.body for item in outcome.summary.action_items] == [
            "confirm the api"
        ]
        assert outcome.summary.action_items[0].source_utterance_ids == [ids[1]]
        assert outcome.dropped == []
        assert outcome.errors == []
    finally:
        store.close()


async def test_summarize_meeting_drops_action_items_citing_unknown_utterances(
    tmp_path: Any,
) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id, ids = _seed(store)
        model = FakeStructuredChatModel(
            [
                _ok(
                    {
                        "decisions": [],
                        "risks": [],
                        "questions": [],
                        "action_items": [
                            {"body": "grounded work", "source_utterance_ids": [ids[0]]},
                            {
                                "body": "hallucinated work",
                                "source_utterance_ids": ["u-does-not-exist"],
                            },
                            {
                                "body": "unsupported work",
                                "source_utterance_ids": [UNKNOWN_SOURCE],
                            },
                        ],
                    }
                )
            ]
        )

        outcome = await summarize_meeting(
            store, meeting_id, model_factory=_factory(model), config=AppConfig()
        )

        assert [item.body for item in outcome.summary.action_items] == ["grounded work"]
        assert len(outcome.dropped) == 2
    finally:
        store.close()


async def test_summarize_meeting_of_an_empty_transcript_calls_no_model(
    tmp_path: Any,
) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = store.create_meeting(title="silent")
        model = FakeStructuredChatModel([])

        outcome = await summarize_meeting(
            store, meeting_id, model_factory=_factory(model), config=AppConfig()
        )

        assert outcome.summary.meeting_id == meeting_id
        assert outcome.summary.decisions == []
        assert outcome.summary.risks == []
        assert outcome.summary.questions == []
        assert outcome.summary.action_items == []
        assert outcome.errors == []
        assert model._schemas == []
    finally:
        store.close()


async def test_summarize_meeting_of_a_noisy_transcript_invents_no_action_items(
    tmp_path: Any,
) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id, _ = _seed(store, ("uh", "hmm", "[inaudible]"))
        model = FakeStructuredChatModel(
            [_ok({"decisions": [], "risks": [], "questions": [], "action_items": []})]
        )

        outcome = await summarize_meeting(
            store, meeting_id, model_factory=_factory(model), config=AppConfig()
        )

        assert outcome.summary.action_items == []
        assert outcome.dropped == []
    finally:
        store.close()


async def test_summarize_meeting_repairs_malformed_model_output(tmp_path: Any) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id, ids = _seed(store)
        model = FakeStructuredChatModel(
            [
                _bad("decisions: field required"),
                _ok(
                    {
                        "decisions": [
                            {"body": "ship on friday", "source_utterance_ids": [ids[0]]}
                        ],
                        "risks": [],
                        "questions": [],
                        "action_items": [],
                    }
                ),
            ]
        )

        outcome = await summarize_meeting(
            store, meeting_id, model_factory=_factory(model), config=AppConfig()
        )

        assert [point.body for point in outcome.summary.decisions] == ["ship on friday"]
        assert outcome.errors == []
        assert model._structured is not None
        assert len(model._structured.calls) == 2
    finally:
        store.close()


async def test_summarize_meeting_degrades_to_empty_when_repair_is_exhausted(
    tmp_path: Any,
) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id, _ = _seed(store)
        model = FakeStructuredChatModel(
            [_bad("nope-1"), _bad("nope-2"), _bad("nope-3")]
        )

        outcome = await summarize_meeting(
            store, meeting_id, model_factory=_factory(model), config=AppConfig()
        )

        assert outcome.summary.action_items == []
        assert outcome.summary.decisions == []
        assert len(outcome.errors) == 1
        assert "nope-3" in outcome.errors[0]
    finally:
        store.close()


async def test_summarize_meeting_degrades_when_the_schema_fails_validation(
    tmp_path: Any,
) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id, _ = _seed(store)
        model = FakeStructuredChatModel(
            [_ok({"decisions": [{"body": "x", "source_utterance_ids": []}]})]
        )

        outcome = await summarize_meeting(
            store, meeting_id, model_factory=_factory(model), config=AppConfig()
        )

        assert outcome.summary.decisions == []
        assert len(outcome.errors) == 1
    finally:
        store.close()


async def test_summarize_meeting_reports_a_provider_failure_without_raising(
    tmp_path: Any,
) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id, _ = _seed(store)
        model = FakeStructuredChatModel(
            raises=ProviderUnavailableError("ollama is down")
        )

        outcome = await summarize_meeting(
            store, meeting_id, model_factory=_factory(model), config=AppConfig()
        )

        assert outcome.summary.action_items == []
        assert len(outcome.errors) == 1
        assert "ollama is down" in outcome.errors[0]
    finally:
        store.close()


def test_action_item_is_the_shared_citation_carrying_type() -> None:
    item = ActionItem(body="ship it", source_utterance_ids=["u-1"])
    summary = MeetingSummary(meeting_id="m-1", action_items=[item])

    assert summary.action_items[0].source_utterance_ids == ["u-1"]
