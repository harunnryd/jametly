from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..config import AppConfig
from ..db import LocalStore, StoreError
from ..llm import ChatMessage, ChatModel, build_chat_model
from ..protocol import ErrorBody, ErrorCode, Event, Reply, Request
from .checkpoint import load_ask_state, save_ask_state
from .state import AskState, Citation
from .tools import (
    TOOL_REGISTRY,
    ToolMutationError,
    UnknownToolError,
    invoke_tool,
)

MAX_CONTEXT_UTTERANCES = 20
MAX_CONTEXT_CHARS = 8000
MAX_TOOL_ITERATIONS = 2
DEFAULT_DEADLINE_S = 30.0
STREAM_EVENT = "stream.event"

ASK_STATE = "ask.state"
ASK_TOKEN = "ask.token"
ASK_DONE = "ask.done"
ASK_ERROR = "ask.error"
ASK_CITATION = "ask.citation"
ASK_TOOL_CALL = "ask.tool_call"
ASK_TOOL_RESULT = "ask.tool_result"

SYSTEM_PROMPT = (
    "You are a meeting assistant. Answer the user's question using only the transcript context "
    "provided. Cite utterance IDs from the context window when relevant."
)

CONTEXT_BLOCK_TEMPLATE = (
    "Transcript context (most recent last; speaker, start_ms, text):\n{utterances}"
)

Emit = Callable[[Event], Awaitable[None]]


def stream_event(correlation_id: str, kind: str, **data: object) -> Event:
    return Event(
        method=STREAM_EVENT,
        params={"correlation_id": correlation_id, "kind": kind, **data},
    )


def _err_reply(req_id: str, code: ErrorCode, message: str, retryable: bool = False) -> Reply:
    return Reply(id=req_id, error=ErrorBody(code=code, message=message, retryable=retryable))


def build_context(
    store: LocalStore,
    meeting_id: str,
    *,
    max_utterances: int = MAX_CONTEXT_UTTERANCES,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> list[dict]:
    full = store.get_full_meeting(meeting_id)
    utterances = full["utterances"]
    chosen: list[dict] = []
    budget = max_chars
    for utterance in reversed(utterances):
        if len(chosen) >= max_utterances:
            break
        text_len = len(utterance["text"])
        if budget - text_len < 0 and chosen:
            break
        chosen.append(utterance)
        budget -= text_len
    chosen.reverse()
    return chosen


def _format_utterance(utterance: dict) -> str:
    speaker = utterance["speaker"]
    start_ms = int(utterance["start_ms"])
    text = utterance["text"]
    return f"[{speaker} @ {start_ms}ms] {text}"


def _format_context(utterances: list[dict], *, truncated: bool) -> str:
    if not utterances:
        return ""
    lines = [_format_utterance(u) for u in utterances]
    if truncated:
        lines.append("... (context truncated)")
    return CONTEXT_BLOCK_TEMPLATE.format(utterances="\n".join(lines))


def build_prompt(
    state: AskState,
    utterances: list[dict],
    *,
    truncated: bool = False,
) -> list[ChatMessage]:
    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
    ]
    context_block = _format_context(utterances, truncated=truncated)
    if context_block:
        messages.append(ChatMessage(role="system", content=context_block))
    messages.append(ChatMessage(role="user", content=state.question))
    return messages


def _resolve_meeting_id(
    raw: object,
    *,
    store: LocalStore,
) -> tuple[str | None, ErrorCode | None, str | None]:
    if isinstance(raw, str) and raw:
        return raw, None, None
    active = store.get_active_meeting()
    if active is None:
        return None, ErrorCode.MEETING_NOT_FOUND, "no active meeting and no meeting_id provided"
    return active["id"], None, None


def _resolve_thread_id(raw: object) -> str:
    if isinstance(raw, str) and raw:
        return raw
    return f"ask-{uuid.uuid4()}"


def _resolve_deadline(raw: object) -> float:
    if raw is None:
        return DEFAULT_DEADLINE_S
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError("deadline_s must be a positive number of seconds")
    if raw <= 0:
        raise ValueError("deadline_s must be a positive number of seconds")
    return float(raw)


def _resolve_question(raw: object) -> str:
    if not isinstance(raw, str):
        raise ValueError("`question` must be a non-empty string")
    stripped = raw.strip()
    if not stripped:
        raise ValueError("`question` must be a non-empty string")
    return stripped


def _citation_from_utterance(utterance: dict) -> Citation:
    return Citation(
        utterance_id=str(utterance["id"]),
        speaker=str(utterance["speaker"]),
        start_ms=int(utterance["start_ms"]),
        text_preview=str(utterance["text"])[:240],
    )


async def _emit_citations(
    emit: Emit,
    *,
    correlation_id: str,
    thread_id: str,
    utterances: list[dict],
) -> list[Citation]:
    citations = [_citation_from_utterance(u) for u in utterances]
    for citation in citations:
        await emit(
            stream_event(
                correlation_id,
                ASK_CITATION,
                thread_id=thread_id,
                utterance_id=citation.utterance_id,
                speaker=citation.speaker,
                start_ms=citation.start_ms,
                text_preview=citation.text_preview,
            )
        )
    return citations


async def _run_tool_path(
    request: Request,
    emit: Emit,
    *,
    store: LocalStore,
    thread_id: str,
    tool: str,
    tool_args: dict,
) -> Reply:
    if tool not in TOOL_REGISTRY:
        return _err_reply(
            request.id,
            ErrorCode.INVALID_REQUEST,
            f"unknown tool: {tool!r}",
        )
    if TOOL_REGISTRY[tool].mutates:
        return _err_reply(
            request.id,
            ErrorCode.INVALID_REQUEST,
            f"tool {tool!r} is mutating and not allowed in ask",
        )
    await emit(
        stream_event(
            request.id,
            ASK_TOOL_CALL,
            thread_id=thread_id,
            tool=tool,
            args=tool_args,
        )
    )
    try:
        result = invoke_tool(tool, tool_args, store=store)
        error_payload: dict | None = None
    except UnknownToolError:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, f"unknown tool: {tool!r}")
    except ToolMutationError:
        return _err_reply(
            request.id,
            ErrorCode.INVALID_REQUEST,
            f"tool {tool!r} is mutating and not allowed in ask",
        )
    except ValueError as exc:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, str(exc))
    await emit(
        stream_event(
            request.id,
            ASK_TOOL_RESULT,
            thread_id=thread_id,
            tool=tool,
            ok=error_payload is None,
            result=result,
        )
    )
    await emit(stream_event(request.id, ASK_DONE, thread_id=thread_id, tool=tool))
    return Reply(
        id=request.id,
        result={
            "thread_id": thread_id,
            "tool": tool,
            "result": result,
        },
    )


async def handle_ask_stream(
    request: Request,
    emit: Emit,
    *,
    store: LocalStore,
    config: AppConfig,
    model_factory: Callable[..., ChatModel] = build_chat_model,
    task_registry: Any = None,
) -> Reply:
    params = request.params if isinstance(request.params, dict) else {}

    try:
        question = _resolve_question(params.get("question"))
    except ValueError as exc:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, str(exc))

    meeting_id, err_code, err_message = _resolve_meeting_id(params.get("meeting_id"), store=store)
    if err_code is not None:
        return _err_reply(request.id, err_code, err_message or "meeting_id resolution failed")

    thread_id = _resolve_thread_id(params.get("thread_id"))

    try:
        deadline_s = _resolve_deadline(params.get("deadline_s"))
    except ValueError as exc:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, str(exc))

    tool = params.get("tool")
    if isinstance(tool, str) and tool:
        tool_args = params.get("tool_args") if isinstance(params.get("tool_args"), dict) else {}
        return await _run_tool_path(
            request,
            emit,
            store=store,
            thread_id=thread_id,
            tool=tool,
            tool_args=tool_args,
        )

    state = load_ask_state(store, meeting_id, thread_id)
    if state is None:
        state = AskState(thread_id=thread_id, meeting_id=meeting_id, question=question)
    else:
        state.question = question

    try:
        context = build_context(store, meeting_id)
    except StoreError as exc:
        return _err_reply(request.id, ErrorCode.MEETING_NOT_FOUND, str(exc))

    provider_id = params.get("provider_id") or config.ai_provider
    model_name = params.get("model") or config.ai_model

    try:
        model = model_factory(provider_id, model_name=model_name)
    except ValueError as exc:
        text = str(exc)
        if "unknown provider" in text:
            return _err_reply(request.id, ErrorCode.PROVIDER_UNAVAILABLE, text)
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, text)

    await emit(stream_event(request.id, ASK_STATE, thread_id=thread_id, state="started"))

    messages = build_prompt(state, context)
    answer_tokens: list[str] = []

    async def stream_tokens() -> None:
        async for token in model.stream(messages):
            answer_tokens.append(token)
            await emit(stream_event(request.id, ASK_TOKEN, thread_id=thread_id, data=token))

    try:
        await asyncio.wait_for(stream_tokens(), timeout=deadline_s)
    except asyncio.TimeoutError:
        await emit(stream_event(request.id, ASK_STATE, thread_id=thread_id, state="timeout"))
        await emit(
            stream_event(
                request.id,
                ASK_ERROR,
                thread_id=thread_id,
                code=ErrorCode.PYTHON_TIMEOUT.value,
                message=f"ask exceeded {deadline_s}s",
            )
        )
        return _err_reply(
            request.id,
            ErrorCode.PYTHON_TIMEOUT,
            f"ask exceeded {deadline_s}s",
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        code, message = _classify(exc)
        await emit(
            stream_event(
                request.id,
                ASK_ERROR,
                thread_id=thread_id,
                code=code.value,
                message=message,
            )
        )
        retryable = bool(getattr(exc, "retryable", False))
        return _err_reply(request.id, code, message, retryable=retryable)

    answer = "".join(answer_tokens)
    state.answer = answer
    state.context_utterance_ids = [str(u["id"]) for u in context]
    save_ask_state(store, state)

    citations = await _emit_citations(
        emit,
        correlation_id=request.id,
        thread_id=thread_id,
        utterances=context,
    )

    await emit(stream_event(request.id, ASK_STATE, thread_id=thread_id, state="completed"))
    await emit(
        stream_event(
            request.id,
            ASK_DONE,
            thread_id=thread_id,
            answer_chars=len(answer),
            citations=len(citations),
        )
    )

    return Reply(
        id=request.id,
        result={
            "thread_id": thread_id,
            "meeting_id": meeting_id,
            "answer": answer,
            "citations": [c.model_dump(mode="json") for c in citations],
        },
    )


def _classify(exc: BaseException) -> tuple[ErrorCode, str]:
    from .chat import _classify_provider_error
    return _classify_provider_error(exc)


async def handle_ask_cancel(
    request: Request,
    emit: Emit,
    *,
    task_registry: Any,
    store: LocalStore | None = None,
) -> Reply:
    thread_id = request.params.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, "thread_id is required")
    if task_registry is None:
        return _err_reply(
            request.id,
            ErrorCode.INTERNAL,
            "ask cancel requires a task registry",
        )
    cancelled = task_registry.cancel_thread(thread_id)
    return Reply(
        id=request.id,
        result={"thread_id": thread_id, "cancelled": cancelled},
    )
