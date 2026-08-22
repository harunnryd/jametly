from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from jamly.agent.chat import ProviderUnavailableError
from jamly.config import AppConfig
from jamly.db import LocalStore
from jamly.meetings import PostProcessResult, run_post_process
from jamly.meetings.extractor import FOLLOWUP_EMIT, FOLLOWUP_KINDS, UNKNOWN_SOURCE
from jamly.protocol import Event


class EventRecorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    async def __call__(self, event: Event) -> None:
        self.events.append(event)

    def followups(self) -> list[dict[str, Any]]:
        return [event.params for event in self.events if event.method == FOLLOWUP_EMIT]


class BoundStructured:
    def __init__(self, outcomes: list[dict[str, Any]]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[list[Any]] = []

    async def ainvoke(self, messages: list[Any]) -> dict[str, Any]:
        self.calls.append(list(messages))
        if not self._outcomes:
            raise AssertionError("structured runnable invoked more times than planned")
        return self._outcomes.pop(0)


class ScriptedChatModel(BaseChatModel):
    _binds: list[list[dict[str, Any]]]
    _raises: BaseException | None
    _bound: list[BoundStructured]

    def __init__(
        self,
        binds: list[list[dict[str, Any]]] | None = None,
        raises: BaseException | None = None,
    ) -> None:
        super().__init__()
        self._binds = [list(bind) for bind in (binds or [])]
        self._raises = raises
        self._bound = []

    @property
    def _llm_type(self) -> str:
        return "followups-scripted-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        raise AssertionError(
            "post-processing must use structured output, not _generate"
        )

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        if self._raises is not None:
            raise self._raises
        if not self._binds:
            raise AssertionError("structured output bound more times than planned")
        bound = BoundStructured(self._binds.pop(0))
        self._bound.append(bound)
        return bound


def _ok(parsed: dict[str, Any]) -> dict[str, Any]:
    return {"raw": "raw-text", "parsed": parsed, "parsing_error": None}


def _bad(error: str) -> dict[str, Any]:
    return {"raw": "raw-text", "parsed": None, "parsing_error": ValueError(error)}


def _factory(model: BaseChatModel) -> Callable[..., BaseChatModel]:
    def factory(provider_id: str, *, model_name: str) -> BaseChatModel:
        return model

    return factory


def _empty_summary() -> dict[str, Any]:
    return {"decisions": [], "risks": [], "questions": [], "action_items": []}


def _seed(store: LocalStore, texts: tuple[str, ...]) -> tuple[str, list[str]]:
    meeting_id = store.create_meeting(title="weekly")
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


async def test_post_process_emits_one_event_per_followup_kind(tmp_path: Any) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    recorder = EventRecorder()
    try:
        meeting_id, ids = _seed(
            store, ("we ship friday", "no we ship monday", "who tells the client")
        )
        model = ScriptedChatModel(
            [
                [_ok(_empty_summary())],
                [
                    _ok(
                        {
                            "items": [
                                {
                                    "kind": "question",
                                    "body": "who tells the client",
                                    "source_utterance_ids": [ids[2]],
                                },
                                {
                                    "kind": "contradiction",
                                    "body": "friday versus monday",
                                    "source_utterance_ids": [ids[1]],
                                },
                                {
                                    "kind": "action",
                                    "body": "email the client",
                                    "source_utterance_ids": [ids[2]],
                                },
                                {
                                    "kind": "todo",
                                    "body": "pick a date",
                                    "source_utterance_ids": [ids[0]],
                                },
                            ]
                        }
                    )
                ],
            ]
        )

        result = await run_post_process(
            store,
            meeting_id,
            recorder,
            model_factory=_factory(model),
            config=AppConfig(),
        )

        assert isinstance(result, PostProcessResult)
        emitted = recorder.followups()
        assert [params["kind"] for params in emitted] == list(FOLLOWUP_KINDS)
        assert {params["meeting_id"] for params in emitted} == {meeting_id}
        assert all(params["body"] for params in emitted)
        assert [followup.kind for followup in result.followups] == list(FOLLOWUP_KINDS)
    finally:
        store.close()


async def test_post_process_stamps_followups_from_their_cited_utterance(
    tmp_path: Any,
) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    recorder = EventRecorder()
    try:
        meeting_id, ids = _seed(store, ("first", "second", "third"))
        model = ScriptedChatModel(
            [
                [_ok(_empty_summary())],
                [
                    _ok(
                        {
                            "items": [
                                {
                                    "kind": "todo",
                                    "body": "do the thing",
                                    "source_utterance_ids": [ids[2]],
                                }
                            ]
                        }
                    )
                ],
            ]
        )

        await run_post_process(
            store,
            meeting_id,
            recorder,
            model_factory=_factory(model),
            config=AppConfig(),
        )

        emitted = recorder.followups()
        assert len(emitted) == 1
        assert emitted[0]["ts_ms"] == 2000
        assert emitted[0]["citations"] == [ids[2]]
    finally:
        store.close()


async def test_post_process_never_emits_an_ungrounded_followup(tmp_path: Any) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    recorder = EventRecorder()
    try:
        meeting_id, ids = _seed(store, ("alpha", "beta"))
        model = ScriptedChatModel(
            [
                [_ok(_empty_summary())],
                [
                    _ok(
                        {
                            "items": [
                                {
                                    "kind": "action",
                                    "body": "real",
                                    "source_utterance_ids": [ids[0]],
                                },
                                {
                                    "kind": "action",
                                    "body": "invented",
                                    "source_utterance_ids": ["u-nope"],
                                },
                                {
                                    "kind": "todo",
                                    "body": "unsupported",
                                    "source_utterance_ids": [UNKNOWN_SOURCE],
                                },
                            ]
                        }
                    )
                ],
            ]
        )

        result = await run_post_process(
            store,
            meeting_id,
            recorder,
            model_factory=_factory(model),
            config=AppConfig(),
        )

        assert [params["body"] for params in recorder.followups()] == ["real"]
        assert len(result.dropped) == 2
    finally:
        store.close()


async def test_post_process_of_an_empty_meeting_emits_nothing(tmp_path: Any) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    recorder = EventRecorder()
    try:
        meeting_id = store.create_meeting(title="silent")
        model = ScriptedChatModel([])

        result = await run_post_process(
            store,
            meeting_id,
            recorder,
            model_factory=_factory(model),
            config=AppConfig(),
        )

        assert recorder.followups() == []
        assert result.followups == []
        assert result.summary.action_items == []
        assert result.errors == []
    finally:
        store.close()


async def test_post_process_still_returns_the_summary_when_followups_fail(
    tmp_path: Any,
) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    recorder = EventRecorder()
    try:
        meeting_id, ids = _seed(store, ("we ship friday",))
        model = ScriptedChatModel(
            [
                [
                    _ok(
                        {
                            "decisions": [
                                {
                                    "body": "ship on friday",
                                    "source_utterance_ids": [ids[0]],
                                }
                            ],
                            "risks": [],
                            "questions": [],
                            "action_items": [],
                        }
                    )
                ],
                [_bad("kind: invalid"), _bad("kind: invalid"), _bad("kind: invalid")],
            ]
        )

        result = await run_post_process(
            store,
            meeting_id,
            recorder,
            model_factory=_factory(model),
            config=AppConfig(),
        )

        assert [point.body for point in result.summary.decisions] == ["ship on friday"]
        assert result.followups == []
        assert recorder.followups() == []
        assert len(result.errors) == 1
    finally:
        store.close()


async def test_post_process_reports_a_dead_provider_without_raising(
    tmp_path: Any,
) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    recorder = EventRecorder()
    try:
        meeting_id, _ = _seed(store, ("we ship friday",))
        model = ScriptedChatModel(raises=ProviderUnavailableError("ollama is down"))

        result = await run_post_process(
            store,
            meeting_id,
            recorder,
            model_factory=_factory(model),
            config=AppConfig(),
        )

        assert result.summary.action_items == []
        assert result.followups == []
        assert recorder.followups() == []
        assert len(result.errors) == 2
        assert all("ollama is down" in error for error in result.errors)
    finally:
        store.close()


async def test_post_process_of_a_missing_meeting_reports_not_found(
    tmp_path: Any,
) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    recorder = EventRecorder()
    try:
        model = ScriptedChatModel([])

        result = await run_post_process(
            store,
            "no-such-meeting",
            recorder,
            model_factory=_factory(model),
            config=AppConfig(),
        )

        assert result.summary.action_items == []
        assert result.followups == []
        assert recorder.followups() == []
        assert len(result.errors) == 1
    finally:
        store.close()


@pytest.mark.network
async def test_real_provider_honours_the_grounded_schema(tmp_path: Any) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    recorder = EventRecorder()
    try:
        meeting_id, ids = _seed(
            store,
            (
                "we agreed to ship the installer on friday",
                "actually monday is safer, friday is too tight",
                "who is telling the customer about the slip",
            ),
        )

        result = await run_post_process(store, meeting_id, recorder, config=AppConfig())

        assert result.summary.meeting_id == meeting_id
        allowed = {*ids, UNKNOWN_SOURCE}
        for section in (
            result.summary.decisions,
            result.summary.risks,
            result.summary.questions,
            result.summary.action_items,
        ):
            for entry in section:
                assert set(entry.source_utterance_ids) <= allowed
        for followup in result.followups:
            assert followup.kind in FOLLOWUP_KINDS
            assert set(followup.source_utterance_ids) <= set(ids)
        assert [params["kind"] for params in recorder.followups()] == [
            followup.kind for followup in result.followups
        ]
    finally:
        store.close()
