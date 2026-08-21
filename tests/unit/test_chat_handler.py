from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

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
from jamly.llm import ChatMessage, ChatModel, ProviderRegistry, build_chat_model
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
        return [event.params["data"] for event in self.of_kind("chat.token")]


def _fake_factory(
    tokens: tuple[str, ...] = ("hello", "there"), **kwargs: object
) -> Callable[..., ChatModel]:
    def factory(provider_id: str, *, model_name: str) -> ChatModel:
        return FakeChatModel(
            tokens=tokens,
            provider_id=provider_id,
            model_name=model_name,
            **kwargs,
        )

    return factory


def _store_factory(model: FakeChatModel):
    def factory(provider_id: str, *, model_name: str) -> ChatModel:
        model.provider_id = provider_id
        model.model_name = model_name
        return model

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

    reply = await handle_chat_stream(
        request,
        emit,
        config=_config(),
        model_factory=lambda *_, **__: FakeChatModel(
            tokens=("a", "b", "c"), delay_ms=50
        ),
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
        def factory(*_: object, **__: object) -> ChatModel:
            class _Boom:
                provider_id = "boom"
                model_name = "m"

                async def stream(self_inner, messages: object):
                    raise exc
                    yield ""

                def invoke(self_inner, messages: object) -> str:
                    raise exc

            return _Boom()

        request = Request(
            id=f"err-{expected.value}",
            method="chat.stream",
            params={"messages": [{"role": "user", "content": "x"}]},
        )
        emit = EventRecorder()
        reply = await handle_chat_stream(request, emit, config=_config(), model_factory=factory)

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
        json.loads(json.dumps(__import__("tomllib").loads(config_path.read_text())))
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
