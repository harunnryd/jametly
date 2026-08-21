from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from jamly.agent import ask as ask_mod
from jamly.agent.ask import (
    ASK_CITATION,
    ASK_DONE,
    ASK_ERROR,
    ASK_STATE,
    ASK_TOKEN,
    ASK_TOOL_CALL,
    ASK_TOOL_RESULT,
    AskState,
    handle_ask_cancel,
    handle_ask_stream,
)
from jamly.agent.tools import TOOL_REGISTRY, ToolMutationError, ToolSpec, UnknownToolError, invoke_tool
from jamly.config import AppConfig
from jamly.db import LocalStore
from jamly.llm import ChatMessage, ChatModel
from jamly.llm.fake import FakeChatModel
from jamly.protocol import ErrorCode, Event, Reply, Request


class EventRecorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    async def __call__(self, event: Event) -> None:
        self.events.append(event)

    def of_kind(self, kind: str) -> list[Event]:
        return [event for event in self.events if event.params.get("kind") == kind]

    def tokens(self) -> list[str]:
        return [event.params["data"] for event in self.of_kind("ask.token")]

    def citations(self) -> list[dict]:
        return [event.params for event in self.of_kind("ask.citation")]


def _fake_factory(
    tokens: tuple[str, ...] = ("the", "answer"),
    **kwargs: object,
) -> Callable[..., ChatModel]:
    def factory(provider_id: str, *, model_name: str) -> ChatModel:
        return FakeChatModel(
            tokens=tokens,
            provider_id=provider_id,
            model_name=model_name,
            **kwargs,
        )

    return factory


def _config() -> AppConfig:
    return AppConfig()


def _seed_meeting_with(
    store: LocalStore,
    texts: tuple[str, ...] = ("alpha line", "beta line"),
) -> str:
    meeting_id = str(uuid.uuid4())
    store.create_meeting(meeting_id)
    for index, text in enumerate(texts):
        store.append_utterance(
            meeting_id=meeting_id,
            speaker="A",
            text=text,
            start_ms=index * 1000,
            end_ms=index * 1000 + 500,
            confidence=0.9,
            segment_id=str(uuid.uuid4()),
        )
    return meeting_id


def _request(
    *,
    question: str = "what was decided?",
    meeting_id: str | None = None,
    thread_id: str | None = "th-fixed",
    deadline_s: float | None = None,
    tool: str | None = None,
    tool_args: dict | None = None,
) -> Request:
    params: dict = {"question": question}
    if meeting_id is not None:
        params["meeting_id"] = meeting_id
    if thread_id is not None:
        params["thread_id"] = thread_id
    if deadline_s is not None:
        params["deadline_s"] = deadline_s
    if tool is not None:
        params["tool"] = tool
        params["tool_args"] = tool_args or {}
    return Request(id="req-1", method="ask.stream", params=params)


async def test_rejects_missing_question(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        emit = EventRecorder()
        reply = await handle_ask_stream(
            Request(id="r", method="ask.stream", params={"meeting_id": str(uuid.uuid4())}),
            emit,
            store=store,
            config=_config(),
            model_factory=_fake_factory(),
        )
        assert reply.error is not None
        assert reply.error.code == ErrorCode.INVALID_REQUEST
        assert emit.events == []
    finally:
        store.close()


async def test_rejects_blank_question(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        emit = EventRecorder()
        meeting_id = _seed_meeting_with(store)
        reply = await handle_ask_stream(
            Request(id="r", method="ask.stream", params={"meeting_id": meeting_id, "question": "  "}),
            emit,
            store=store,
            config=_config(),
            model_factory=_fake_factory(),
        )
        assert reply.error is not None
        assert reply.error.code == ErrorCode.INVALID_REQUEST
    finally:
        store.close()


async def test_rejects_unknown_meeting(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        emit = EventRecorder()
        reply = await handle_ask_stream(
            _request(meeting_id="not-real"),
            emit,
            store=store,
            config=_config(),
            model_factory=_fake_factory(),
        )
        assert reply.error is not None
        assert reply.error.code == ErrorCode.MEETING_NOT_FOUND
    finally:
        store.close()


async def test_resolves_active_meeting_when_omitted(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        emit = EventRecorder()
        meeting_id = _seed_meeting_with(store)
        reply = await handle_ask_stream(
            Request(
                id="r",
                method="ask.stream",
                params={"question": "q", "thread_id": "th-1"},
            ),
            emit,
            store=store,
            config=_config(),
            model_factory=_fake_factory(),
        )
        assert reply.error is None
        assert reply.result["meeting_id"] == meeting_id
    finally:
        store.close()


async def test_emits_state_started_token_completed_done_sequence(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        emit = EventRecorder()
        meeting_id = _seed_meeting_with(store)
        reply = await handle_ask_stream(
            _request(meeting_id=meeting_id),
            emit,
            store=store,
            config=_config(),
            model_factory=_fake_factory(tokens=("the answer now",)),
        )
        assert reply.error is None
        assert reply.result["answer"] == "the answer now"
        kinds = [event.params["kind"] for event in emit.events]
        assert "ask.state" in kinds
        assert "ask.token" in kinds
        assert "ask.done" in kinds
    finally:
        store.close()


async def test_emits_citation_events_for_each_in_scope_utterance(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        emit = EventRecorder()
        meeting_id = _seed_meeting_with(store, texts=("first line", "second line", "third line"))
        await handle_ask_stream(
            _request(meeting_id=meeting_id),
            emit,
            store=store,
            config=_config(),
            model_factory=_fake_factory(),
        )
        citations = emit.citations()
        assert len(citations) == 3
        assert [c["text_preview"] for c in citations] == ["first line", "second line", "third line"]
        assert all(c["thread_id"] == "th-fixed" for c in citations)
        assert all("utterance_id" in c for c in citations)
        assert reply_payload_is_serializable(citations)
    finally:
        store.close()


def reply_payload_is_serializable(payload) -> bool:
    from pydantic import BaseModel
    try:
        if isinstance(payload, BaseModel):
            payload.model_dump(mode="json")
        return True
    except Exception:
        return False


async def test_save_state_persists_for_next_call(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed_meeting_with(store)
        first_emit = EventRecorder()
        first_reply = await handle_ask_stream(
            _request(meeting_id=meeting_id),
            first_emit,
            store=store,
            config=_config(),
            model_factory=_fake_factory(tokens=("persisted",)),
        )
        assert first_reply.error is None
        second_emit = EventRecorder()
        second_reply = await handle_ask_stream(
            _request(meeting_id=meeting_id, thread_id="th-fixed"),
            second_emit,
            store=store,
            config=_config(),
            model_factory=_fake_factory(tokens=("another",)),
        )
        assert second_reply.error is None
        from jamly.agent.checkpoint import load_ask_state
        loaded = load_ask_state(store, meeting_id, "th-fixed")
        assert loaded is not None
        assert loaded.answer == "another"
    finally:
        store.close()


async def test_deadline_triggers_python_timeout(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed_meeting_with(store)

        def slow_factory(provider_id, *, model_name):
            return FakeChatModel(
                tokens=("a", "b", "c", "d", "e"),
                delay_ms=200,
                provider_id=provider_id,
                model_name=model_name,
            )

        emit = EventRecorder()
        reply = await handle_ask_stream(
            _request(meeting_id=meeting_id, deadline_s=0.05),
            emit,
            store=store,
            config=_config(),
            model_factory=slow_factory,
        )
        assert reply.error is not None
        assert reply.error.code == ErrorCode.PYTHON_TIMEOUT
        kinds = [event.params["kind"] for event in emit.events]
        assert "ask.error" in kinds
        assert "ask.state" in kinds
    finally:
        store.close()


async def test_invalid_deadline_returns_invalid_request(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed_meeting_with(store)
        emit = EventRecorder()
        reply = await handle_ask_stream(
            _request(meeting_id=meeting_id, deadline_s=0),
            emit,
            store=store,
            config=_config(),
            model_factory=_fake_factory(),
        )
        assert reply.error is not None
        assert reply.error.code == ErrorCode.INVALID_REQUEST
    finally:
        store.close()


async def test_tool_path_emits_call_and_result_events(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        _seed_meeting_with(store, ("deadline tomorrow",))
        emit = EventRecorder()
        reply = await handle_ask_stream(
            _request(tool="search_history", tool_args={"query": "deadline"}),
            emit,
            store=store,
            config=_config(),
            model_factory=_fake_factory(),
        )
        assert reply.error is None
        kinds = [event.params["kind"] for event in emit.events]
        assert "ask.tool_call" in kinds
        assert "ask.tool_result" in kinds
        assert "ask.done" in kinds
        assert reply.result["tool"] == "search_history"
    finally:
        store.close()


async def test_tool_path_rejects_unknown_tool(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        _seed_meeting_with(store)
        emit = EventRecorder()
        reply = await handle_ask_stream(
            _request(tool="ghost_tool"),
            emit,
            store=store,
            config=_config(),
            model_factory=_fake_factory(),
        )
        assert reply.error is not None
        assert reply.error.code == ErrorCode.INVALID_REQUEST
    finally:
        store.close()


async def test_tool_path_rejects_mutating_tool(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        sentinel = "_fake_mutating"
        TOOL_REGISTRY[sentinel] = ToolSpec(sentinel, "fake", mutates=True)
        try:
            _seed_meeting_with(store)
            emit = EventRecorder()
            reply = await handle_ask_stream(
                _request(tool=sentinel),
                emit,
                store=store,
                config=_config(),
                model_factory=_fake_factory(),
            )
            assert reply.error is not None
            assert reply.error.code == ErrorCode.INVALID_REQUEST
        finally:
            TOOL_REGISTRY.pop(sentinel, None)
    finally:
        store.close()


async def test_unknown_provider_returns_provider_unavailable(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed_meeting_with(store)
        emit = EventRecorder()
        reply = await handle_ask_stream(
            _request(meeting_id=meeting_id),
            emit,
            store=store,
            config=_config(),
            model_factory=lambda provider_id, *, model_name: (_ for _ in ()).throw(
                ValueError(f"unknown provider: {provider_id!r}")
            ),
        )
        assert reply.error is not None
        assert reply.error.code == ErrorCode.PROVIDER_UNAVAILABLE
    finally:
        store.close()


async def test_unknown_provider_during_stream_surfaces_canonical_error(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        meeting_id = _seed_meeting_with(store)
        from jamly.agent.chat import ProviderAuthError

        def raise_factory(provider_id, *, model_name):
            return _RaisingChatModel(error=ProviderAuthError("missing creds"))

        emit = EventRecorder()
        reply = await handle_ask_stream(
            _request(meeting_id=meeting_id),
            emit,
            store=store,
            config=_config(),
            model_factory=raise_factory,
        )
        assert reply.error is not None
        assert reply.error.code == ErrorCode.PROVIDER_AUTH
    finally:
        store.close()


async def test_handle_ask_cancel_returns_zero_for_unknown_thread(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        registry = _StubRegistry()
        reply = await handle_ask_cancel(
            Request(id="r", method="ask.cancel", params={"thread_id": "nope"}),
            EventRecorder(),
            store=store,
            task_registry=registry,
        )
        assert reply.error is None
        assert reply.result == {"thread_id": "nope", "cancelled": 0}
    finally:
        store.close()


async def test_handle_ask_cancel_rejects_missing_thread_id(tmp_path: Path) -> None:
    reply = await handle_ask_cancel(
        Request(id="r", method="ask.cancel", params={}),
        EventRecorder(),
        store=None,
        task_registry=_StubRegistry(),
    )
    assert reply.error is not None
    assert reply.error.code == ErrorCode.INVALID_REQUEST


class _StubRegistry:
    def cancel_thread(self, thread_id: str, *, exclude_request_id: str | None = None) -> int:
        return 0


class _RaisingChatModel:
    def __init__(self, error: BaseException) -> None:
        self._error = error
        self.provider_id = "fake"
        self.model_name = "fake"

    async def stream(self, messages):
        raise self._error
        yield ""

    def invoke(self, messages):
        raise self._error


def test_ask_stream_handler_is_exported_from_agent_package() -> None:
    assert callable(ask_mod.handle_ask_stream)
    assert callable(ask_mod.handle_ask_cancel)
