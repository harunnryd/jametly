from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage, SystemMessage

from ..config import AppConfig, load_config, save_config
from ..llm import (
    ChatMessage,
    ProviderKind,
    ProviderRegistry,
    build_chat_model,
)
from ..protocol import ErrorBody, ErrorCode, Event, Reply, Request

Emit = Callable[[Event], Awaitable[None]]

CHAT_STATE = "chat.state"
CHAT_TOKEN = "chat.token"
CHAT_DONE = "chat.done"
CHAT_ERROR = "chat.error"
STREAM_EVENT = "stream.event"

DEFAULT_DEADLINE_S = 30.0


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProviderAuthError(ProviderError):
    def __init__(self, message: str = "missing credentials") -> None:
        super().__init__(message, retryable=False)


class ProviderRateLimitError(ProviderError):
    def __init__(self, message: str = "rate limited") -> None:
        super().__init__(message, retryable=True)


class ProviderUnavailableError(ProviderError):
    def __init__(self, message: str = "provider unavailable") -> None:
        super().__init__(message, retryable=False)


class ProviderMalformedResponseError(ProviderError):
    def __init__(self, message: str = "malformed provider response") -> None:
        super().__init__(message, retryable=False)


def stream_event(correlation_id: str, kind: str, **data: object) -> Event:
    return Event(
        method=STREAM_EVENT,
        params={"correlation_id": correlation_id, "kind": kind, **data},
    )


def _classify_provider_error(exc: BaseException) -> tuple[ErrorCode, str]:
    if isinstance(exc, asyncio.TimeoutError):
        return ErrorCode.PYTHON_TIMEOUT, "chat exceeded the configured deadline"
    if isinstance(exc, ProviderAuthError):
        return ErrorCode.PROVIDER_AUTH, str(exc)
    if isinstance(exc, ProviderRateLimitError):
        return ErrorCode.PROVIDER_RATE_LIMIT, str(exc)
    if isinstance(exc, ProviderUnavailableError):
        return ErrorCode.PROVIDER_UNAVAILABLE, str(exc)
    if isinstance(exc, ProviderMalformedResponseError):
        return ErrorCode.PARSE_ERROR, str(exc)
    return ErrorCode.INTERNAL, f"{type(exc).__name__}: {exc}"


def _err_reply(req_id: str, code: ErrorCode, message: str, retryable: bool = False) -> Reply:
    return Reply(id=req_id, error=ErrorBody(code=code, message=message, retryable=retryable))


def _normalize_messages(raw: object) -> list[ChatMessage]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("messages must be a non-empty list")
    messages: list[ChatMessage] = []
    for item in raw:
        if isinstance(item, ChatMessage):
            messages.append(item)
        if isinstance(item, dict):
            messages.append(ChatMessage.model_validate(item))
            continue
        raise ValueError(f"each message must be a dict or ChatMessage, got {type(item).__name__}")
    return messages


def _to_langchain(messages: list[ChatMessage]) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for msg in messages:
        if msg.role == "system":
            out.append(SystemMessage(content=msg.content))
        else:
            out.append(HumanMessage(content=msg.content))
    return out


def _resolve_deadline(raw: object) -> float:
    if raw is None:
        return DEFAULT_DEADLINE_S
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError("deadline_s must be a positive number of seconds")
    if raw <= 0:
        raise ValueError("deadline_s must be a positive number of seconds")
    return float(raw)


def _resolve_thread_id(raw: object) -> str:
    if isinstance(raw, str) and raw:
        return raw
    return f"th-{uuid.uuid4()}"


def _resolve_kind(raw: object) -> ProviderKind:
    if isinstance(raw, ProviderKind):
        return raw
    if isinstance(raw, str):
        try:
            return ProviderKind(raw)
        except ValueError:
            pass
    raise ValueError("kind must be 'ai' or 'stt'")


def _chunk_content(chunk: AIMessageChunk) -> str:
    content = chunk.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return ""


async def handle_chat_stream(
    request: Request,
    emit: Emit,
    *,
    config: AppConfig,
    model_factory: Callable[..., BaseChatModel] = build_chat_model,
) -> Reply:
    try:
        messages = _normalize_messages(request.params.get("messages"))
    except ValueError as exc:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, str(exc))

    provider_id = request.params.get("provider_id") or config.ai_provider
    model_name = request.params.get("model") or config.ai_model

    try:
        deadline_s = _resolve_deadline(request.params.get("deadline_s"))
    except ValueError as exc:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, str(exc))

    thread_id = _resolve_thread_id(request.params.get("thread_id"))

    try:
        model = model_factory(provider_id, model_name=model_name)
    except ValueError as exc:
        text = str(exc)
        if "unknown provider" in text:
            return _err_reply(request.id, ErrorCode.PROVIDER_UNAVAILABLE, text)
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, text)

    await emit(stream_event(request.id, CHAT_STATE, thread_id=thread_id, state="started"))

    tokens: list[str] = []
    lc_messages = _to_langchain(messages)

    async def emit_tokens() -> None:
        async for chunk in model.astream(lc_messages):
            text = _chunk_content(chunk)
            if not text:
                continue
            tokens.append(text)
            await emit(stream_event(request.id, CHAT_TOKEN, thread_id=thread_id, data=text))

    try:
        await asyncio.wait_for(emit_tokens(), timeout=deadline_s)
    except asyncio.TimeoutError:
        await emit(stream_event(request.id, CHAT_STATE, thread_id=thread_id, state="timeout"))
        await emit(
            stream_event(
                request.id,
                CHAT_ERROR,
                thread_id=thread_id,
                code=ErrorCode.PYTHON_TIMEOUT.value,
                message=f"chat exceeded {deadline_s}s",
            )
        )
        return _err_reply(
            request.id,
            ErrorCode.PYTHON_TIMEOUT,
            f"chat exceeded {deadline_s}s",
        )
    except asyncio.CancelledError:
        raise
    except ProviderError as exc:
        code, message = _classify_provider_error(exc)
        await emit(
            stream_event(
                request.id,
                CHAT_ERROR,
                thread_id=thread_id,
                code=code.value,
                message=message,
            )
        )
        return _err_reply(request.id, code, message, retryable=exc.retryable)
    except Exception as exc:
        code, message = _classify_provider_error(exc)
        await emit(
            stream_event(
                request.id,
                CHAT_ERROR,
                thread_id=thread_id,
                code=code.value,
                message=message,
            )
        )
        return _err_reply(request.id, code, message)

    await emit(stream_event(request.id, CHAT_STATE, thread_id=thread_id, state="completed"))
    await emit(stream_event(request.id, CHAT_DONE, thread_id=thread_id, tokens=len(tokens)))

    return Reply(
        id=request.id,
        result={"thread_id": thread_id, "model": model_name, "tokens": len(tokens)},
    )


async def handle_chat_cancel(request: Request, emit: Emit, *, task_registry) -> Reply:
    thread_id = request.params.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, "thread_id is required")
    cancelled = task_registry.cancel_thread(thread_id, exclude_request_id=request.id)
    return Reply(id=request.id, result={"thread_id": thread_id, "cancelled": cancelled})


async def handle_providers_list(
    request: Request,
    emit: Emit,
    *,
    provider_registry: ProviderRegistry,
) -> Reply:
    kind_raw = request.params.get("kind") if isinstance(request.params, dict) else None
    if kind_raw is None:
        providers = provider_registry.list()
    elif isinstance(kind_raw, str):
        providers = provider_registry.list(kind=kind_raw)
    else:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, "kind must be a string")
    return Reply(
        id=request.id,
        result={"providers": [provider.model_dump(mode="json") for provider in providers]},
    )


async def handle_providers_set_selected(
    request: Request,
    emit: Emit,
    *,
    config_path: Path,
) -> Reply:
    params = request.params
    provider_id = params.get("provider_id")
    if not isinstance(provider_id, str) or not provider_id:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, "provider_id is required")

    try:
        kind = _resolve_kind(params.get("kind"))
    except ValueError as exc:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, str(exc))

    registry = ProviderRegistry()
    available = {p.id for p in registry.list(kind=kind)}
    if provider_id not in available:
        return _err_reply(
            request.id,
            ErrorCode.PROVIDER_UNAVAILABLE,
            f"unknown {kind.value} provider: {provider_id}",
        )

    try:
        current = load_config(config_path)
    except FileNotFoundError:
        current = AppConfig()

    field = "ai_provider" if kind is ProviderKind.AI else "stt_provider"
    updated = current.model_copy(update={field: provider_id})
    save_config(config_path, updated)

    return Reply(
        id=request.id,
        result={"kind": kind.value, "provider_id": provider_id},
    )