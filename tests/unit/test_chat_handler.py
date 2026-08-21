from __future__ import annotations

import asyncio
import json
import tomllib
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence  # noqa: F401
from pathlib import Path
from typing import Any

import pytest
import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk

from jamly.agent.chat import (
    ProviderAuthError,
    ProviderMalformedResponseError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    handle_chat_cancel,
    handle_chat_stream,
    handle_providers_list,
    handle_providers_set_selected,
    stream_event,
)
from jamly.config import AppConfig, save_config
from jamly.llm import ChatMessage, ProviderRegistry, build_chat_model
from jamly.protocol import ErrorCode, Event, Reply, Request


class EventRecorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    async def __call__(self, event: Event) -> None:
        self.events.append(event)

    def of_kind(self, kind: str) -> list[Event]:
        return [event for event in self.events if event.params.get("kind") == kind]

    def tokens(self) -> list[str]:
        return [event.params["data"] for event in self.of_kind("chat.token")]


class _ChunkedFakeChatModel(BaseChatModel):
    _tokens: tuple[str, ...]

    def __init__(self, tokens: tuple[str, ...]) -> None:
        super().__init__()
        self._tokens = tokens

    @property
    def _llm_type(self) -> str:
        return "chunked-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        joined = " ".join(str(getattr(m, "content", "")) for m in messages)
        return AIMessage(content=joined)

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        for token in self._tokens:
            yield ChatGenerationChunk(
                message=AIMessageChunk(content=token),
                text=token,
            )


def _fake_factory(
    tokens: tuple[str, ...] = ("hello", "there"),
) -> Callable[..., BaseChatModel]:
    def factory(provider_id: str, *, model_name: str) -> BaseChatModel:
        return _ChunkedFakeChatModel(tokens)

    return factory


class _RaisingChatModel(BaseChatModel):
    _error: BaseException

    def __init__(self, error: BaseException) -> None:
        super().__init__()
        self._error = error

    @property
    def _llm_type(self) -> str:
        return "raising"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        raise self._error

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        raise self._error
        yield ChatGenerationChunk(message=AIMessageChunk(content=""), text="")


def _raising_factory(error: BaseException) -> Callable[..., BaseChatModel]:
    def factory(provider_id: str, *, model_name: str) -> BaseChatModel:
        return _RaisingChatModel(error)

    return factory


def _config(**overrides: object) -> AppConfig:
    return AppConfig(**overrides)


async def test_chat_stream_emits_token_events_with_correlation_and_thread_id() -> None:
    request = Request(
        id="c1",
        method="chat.stream",
        params={
            "messages": [{"role": "user", "content": "hi"}],
            "provider_id": "ollama",
            "model": "qwen2.5:7b-instruct",
            "thread_id": "th-fixed",
        },
    )
    emit = EventRecorder()

    reply = await handle_chat_stream(
        request,
        emit,
        config=_config(),
        model_factory=_fake_factory(("foo", "bar")),
    )

    assert reply.error is None
    assert reply.result == {"thread_id": "th-fixed", "model": "qwen2.5:7b-instruct", "tokens": 2}

    token_events = emit.tokens()
    assert token_events == ["foo", "bar"]
    for event in emit.of_kind("chat.token"):
        assert event.params["correlation_id"] == "c1"
        assert event.params["thread_id"] == "th-fixed"


async def test_chat_stream_emits_started_then_completed_then_done() -> None:
    request = Request(
        id="c2",
        method="chat.stream",
        params={"messages": [{"role": "user", "content": "go"}]},
    )
    emit = EventRecorder()

    reply = await handle_chat_stream(
        request, emit, config=_config(), model_factory=_fake_factory(("hello",))
    )

    assert reply.error is None
    kinds = [event.params.get("kind") for event in emit.events]
    assert kinds[:1] == ["chat.state"]
    assert kinds[-2:] == ["chat.state", "chat.done"]
    assert emit.events[0].params["state"] == "started"
    assert emit.events[-2].params["state"] == "completed"
    assert emit.events[-1].params["tokens"] == 1


async def test_chat_stream_rejects_missing_messages_with_invalid_request() -> None:
    request = Request(id="c3", method="chat.stream", params={})
    emit = EventRecorder()

    reply = await handle_chat_stream(request, emit, config=_config(), model_factory=_fake_factory())

    assert reply.error is not None
    assert reply.error.code == ErrorCode.INVALID_REQUEST
    assert emit.events == []


async def test_chat_stream_rejects_unknown_provider_with_provider_unavailable() -> None:
    request = Request(
        id="c4",
        method="chat.stream",
        params={
            "messages": [{"role": "user", "content": "hi"}],
            "provider_id": "no-such-thing",
        },
    )
    emit = EventRecorder()

    reply = await handle_chat_stream(
        request,
        emit,
        config=_config(),
        model_factory=build_chat_model,
    )

    assert reply.error is not None
    assert reply.error.code == ErrorCode.PROVIDER_UNAVAILABLE


async def test_chat_stream_enforces_a_deadline_and_returns_python_timeout() -> None:
    request = Request(
        id="c5",
        method="chat.stream",
        params={
            "messages": [{"role": "user", "content": "slow"}],
            "deadline_s": 0.05,
        },
    )
    emit = EventRecorder()

    async def slow_stream(*_: object, **__: object) -> AsyncIterator[str]:
        for piece in ("a", "b", "c"):
            await asyncio.sleep(0.05)
            yield piece

    class _SlowChatModel(BaseChatModel):
        async def _astream(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            **kwargs: Any,
        ) -> AsyncIterator[ChatGenerationChunk]:
            async for piece in slow_stream():
                yield ChatGenerationChunk(
                    message=AIMessageChunk(content=piece),
                    text=piece,
                )

        def _generate(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            **kwargs: Any,
        ) -> Any:
            raise NotImplementedError

        @property
        def _llm_type(self) -> str:
            return "slow"

    def slow_factory(*_: object, **__: object) -> BaseChatModel:
        return _SlowChatModel()

    reply = await handle_chat_stream(
        request,
        emit,
        config=_config(),
        model_factory=slow_factory,
    )

    assert reply.error is not None
    assert reply.error.code == ErrorCode.PYTHON_TIMEOUT

    error_events = emit.of_kind("chat.error")
    assert error_events, "expected a chat.error event for the timeout"
    assert error_events[-1].params["code"] == ErrorCode.PYTHON_TIMEOUT.value

    state_kinds = [event.params.get("state") for event in emit.of_kind("chat.state")]
    assert "timeout" in state_kinds


async def test_chat_stream_maps_canonical_provider_errors() -> None:
    cases = [
        (ProviderAuthError("bad key"), ErrorCode.PROVIDER_AUTH),
        (ProviderRateLimitError(), ErrorCode.PROVIDER_RATE_LIMIT),
        (ProviderUnavailableError("down"), ErrorCode.PROVIDER_UNAVAILABLE),
        (ProviderMalformedResponseError("garbled"), ErrorCode.PARSE_ERROR),
    ]

    for exc, expected in cases:
        request = Request(
            id=f"err-{expected.value}",
            method="chat.stream",
            params={"messages": [{"role": "user", "content": "x"}]},
        )
        emit = EventRecorder()
        reply = await handle_chat_stream(
            request,
            emit,
            config=_config(),
            model_factory=_raising_factory(exc),
        )

        assert reply.error is not None, f"{expected.value} did not error"
        assert reply.error.code == expected, f"{expected.value} mapped wrong"


async def test_chat_cancel_returns_zero_cancelled_for_unknown_thread() -> None:
    from jamly.bridge import TaskRegistry

    registry = TaskRegistry()
    request = Request(id="x1", method="chat.cancel", params={"thread_id": "nope"})
    emit = EventRecorder()

    reply = await handle_chat_cancel(request, emit, task_registry=registry)

    assert reply.error is None
    assert reply.result == {"thread_id": "nope", "cancelled": 0}


async def test_chat_cancel_rejects_missing_thread_id_with_invalid_request() -> None:
    from jamly.bridge import TaskRegistry

    registry = TaskRegistry()
    request = Request(id="x2", method="chat.cancel", params={})
    emit = EventRecorder()

    reply = await handle_chat_cancel(request, emit, task_registry=registry)

    assert reply.error is not None
    assert reply.error.code == ErrorCode.INVALID_REQUEST


async def test_providers_list_returns_full_registry_by_default() -> None:
    request = Request(id="p1", method="providers.list", params={})
    emit = EventRecorder()

    reply = await handle_providers_list(
        request, emit, provider_registry=ProviderRegistry()
    )

    assert reply.error is None
    providers = reply.result["providers"]
    assert {provider["id"] for provider in providers} == {"ollama", "faster-whisper"}
    for provider in providers:
        assert provider["default_model"]
        assert provider["kind"] in {"ai", "stt"}


async def test_providers_list_filters_by_kind() -> None:
    request = Request(id="p2", method="providers.list", params={"kind": "stt"})
    emit = EventRecorder()

    reply = await handle_providers_list(
        request, emit, provider_registry=ProviderRegistry()
    )

    assert reply.error is None
    assert {provider["id"] for provider in reply.result["providers"]} == {"faster-whisper"}


async def test_providers_set_selected_persists_to_config_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    save_config(config_path, AppConfig())
    request = Request(
        id="p3",
        method="providers.set_selected",
        params={"kind": "ai", "provider_id": "ollama"},
    )
    emit = EventRecorder()

    reply = await handle_providers_set_selected(request, emit, config_path=config_path)

    assert reply.error is None
    assert reply.result == {"kind": "ai", "provider_id": "ollama"}

    reloaded = AppConfig.model_validate(
        json.loads(json.dumps(tomllib.loads(config_path.read_text())))
    )
    assert reloaded.ai_provider == "ollama"


async def test_providers_set_selected_rejects_unknown_provider() -> None:
    config_path = Path("/tmp/never-written-config.toml")
    request = Request(
        id="p4",
        method="providers.set_selected",
        params={"kind": "ai", "provider_id": "made-up"},
    )
    emit = EventRecorder()

    reply = await handle_providers_set_selected(request, emit, config_path=config_path)

    assert reply.error is not None
    assert reply.error.code == ErrorCode.PROVIDER_UNAVAILABLE


async def test_stream_event_helper_produces_a_carrying_event() -> None:
    event = stream_event("cid-1", "chat.token", thread_id="th-1", data="hello")

    assert event.method == "stream.event"
    assert event.params == {
        "correlation_id": "cid-1",
        "kind": "chat.token",
        "thread_id": "th-1",
        "data": "hello",
    }


class _RaisingChatModel(BaseChatModel):
    _error: BaseException

    def __init__(self, error: BaseException) -> None:
        super().__init__()
        self._error = error

    @property
    def _llm_type(self) -> str:
        return "raising"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        raise self._error

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        raise self._error
        yield ChatGenerationChunk(message=AIMessageChunk(content=""), text="")


def _raising_factory(error: BaseException) -> Callable[..., BaseChatModel]:
    def factory(provider_id: str, *, model_name: str) -> BaseChatModel:
        return _RaisingChatModel(error=error)

    return factory


async def test_chat_stream_maps_httpx_connect_error_to_provider_unavailable() -> None:
    request = Request(
        id="ce1",
        method="chat.stream",
        params={"messages": [{"role": "user", "content": "hi"}]},
    )
    emit = EventRecorder()
    error = httpx.ConnectError("connection refused", request=httpx.Request("POST", "http://x"))

    reply = await handle_chat_stream(
        request,
        emit,
        config=AppConfig(),
        model_factory=_raising_factory(error),
    )

    assert reply.error is not None
    assert reply.error.code == ErrorCode.PROVIDER_UNAVAILABLE
    error_events = emit.of_kind("chat.error")
    assert len(error_events) == 1
    assert error_events[0].params["code"] == "PROVIDER_UNAVAILABLE"


async def test_chat_stream_maps_httpx_timeout_to_provider_unavailable() -> None:
    request = Request(
        id="ce2",
        method="chat.stream",
        params={"messages": [{"role": "user", "content": "hi"}]},
    )
    emit = EventRecorder()

    reply = await handle_chat_stream(
        request,
        emit,
        config=AppConfig(),
        model_factory=_raising_factory(httpx.TimeoutException("read timed out")),
    )

    assert reply.error is not None
    assert reply.error.code == ErrorCode.PROVIDER_UNAVAILABLE


async def test_chat_stream_maps_connection_refused_to_provider_unavailable() -> None:
    request = Request(
        id="ce3",
        method="chat.stream",
        params={"messages": [{"role": "user", "content": "hi"}]},
    )
    emit = EventRecorder()

    reply = await handle_chat_stream(
        request,
        emit,
        config=AppConfig(),
        model_factory=_raising_factory(ConnectionRefusedError("nope")),
    )

    assert reply.error is not None
    assert reply.error.code == ErrorCode.PROVIDER_UNAVAILABLE