from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Awaitable, TextIO

from pydantic import ValidationError

from .audio import handle_transcribe_audio
from .config import AppConfig
from .db import LocalStore
from .llm import ProviderRegistry
from .meetings.session import (
    handle_meeting_get,
    handle_meeting_list,
    handle_meeting_start,
    handle_meeting_stop,
)
from .protocol import ErrorBody, ErrorCode, Event, Reply, Request

STREAM_EVENT = "stream.event"
TOKEN_KIND = "token"
DONE_KIND = "done"
CANCELLED_KIND = "cancelled"

DEFAULT_STREAM_COUNT = 1
THREAD_KEY = "thread_id"

Emit = Callable[[Event], Awaitable[None]]
Handler = Callable[[Request, Emit], Awaitable[Reply]]


def stream_event(correlation_id: str, kind: str, **data: object) -> Event:
    return Event(method=STREAM_EVENT, params={"correlation_id": correlation_id, "kind": kind, **data})


def _err_reply(req_id: str, code: ErrorCode, message: str, retryable: bool = False) -> Reply:
    return Reply(id=req_id, error=ErrorBody(code=code, message=message, retryable=retryable))


def _non_negative_int(params: dict[str, object], key: str, default: int) -> int:
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"`{key}` must be a non-negative integer, got {value!r}")
    return value


class OutboundStream:
    """The single writer for stdout: one NDJSON line per envelope, never interleaved."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._lock = asyncio.Lock()

    async def send(self, envelope: Event | Reply) -> None:
        line = envelope.model_dump_json(exclude_none=True) + "\n"
        async with self._lock:
            self._stream.write(line)
            self._stream.flush()


class TaskRegistry:
    """In-flight handler tasks keyed by request id, with a thread_id index for JAM-0010."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._threads: dict[str, set[str]] = {}

    def register(self, request: Request, task: asyncio.Task[None]) -> None:
        self._tasks[request.id] = task
        thread_id = request.params.get(THREAD_KEY)
        if isinstance(thread_id, str):
            self._threads.setdefault(thread_id, set()).add(request.id)

    def forget(self, request: Request) -> None:
        self._tasks.pop(request.id, None)
        thread_id = request.params.get(THREAD_KEY)
        if isinstance(thread_id, str):
            siblings = self._threads.get(thread_id)
            if siblings is not None:
                siblings.discard(request.id)
                if not siblings:
                    del self._threads[thread_id]

    def cancel(self, request_id: str) -> bool:
        task = self._tasks.get(request_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def cancel_thread(self, thread_id: str) -> int:
        return sum(self.cancel(request_id) for request_id in tuple(self._threads.get(thread_id, ())))

    def cancel_all(self) -> int:
        return sum(self.cancel(request_id) for request_id in tuple(self._tasks))

    def in_flight(self) -> int:
        return len(self._tasks)

    def tasks(self) -> tuple[asyncio.Task[None], ...]:
        return tuple(self._tasks.values())


async def handle_echo(request: Request, emit: Emit) -> Reply:
    return Reply(id=request.id, result=request.params)


async def handle_debug_stream(request: Request, emit: Emit) -> Reply:
    try:
        count = _non_negative_int(request.params, "count", DEFAULT_STREAM_COUNT)
    except ValueError as exc:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, str(exc))

    for index in range(count):
        await emit(stream_event(request.id, TOKEN_KIND, data=str(index)))
    await emit(stream_event(request.id, DONE_KIND))
    return Reply(id=request.id, result={"count": count})


async def handle_debug_sleep(request: Request, emit: Emit) -> Reply:
    try:
        duration_ms = _non_negative_int(request.params, "ms", 0)
    except ValueError as exc:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, str(exc))

    await asyncio.sleep(duration_ms / 1000)
    return Reply(id=request.id, result={"slept_ms": duration_ms})


DEFAULT_HANDLERS: dict[str, Handler] = {
    "echo": handle_echo,
    "debug.stream": handle_debug_stream,
    "debug.sleep": handle_debug_sleep,
    "transcribe.audio": handle_transcribe_audio,
}


def meeting_handlers(store: LocalStore) -> dict[str, Handler]:
    return {
        "meeting.start": lambda req, emit: handle_meeting_start(req, emit, store=store),
        "meeting.stop": lambda req, emit: handle_meeting_stop(req, emit, store=store),
        "meeting.list": lambda req, emit: handle_meeting_list(req, emit, store=store),
        "meeting.get": lambda req, emit: handle_meeting_get(req, emit, store=store),
    }


def chat_handlers(
    config: AppConfig,
    config_path: Path,
    task_registry: TaskRegistry,
    provider_registry: ProviderRegistry,
) -> dict[str, Handler]:
    from .agent.chat import (
        handle_chat_cancel,
        handle_chat_stream,
        handle_providers_list,
        handle_providers_set_selected,
    )

    return {
        "chat.stream": lambda req, emit: handle_chat_stream(req, emit, config=config),
        "chat.cancel": lambda req, emit: handle_chat_cancel(req, emit, task_registry=task_registry),
        "providers.list": lambda req, emit: handle_providers_list(
            req, emit, provider_registry=provider_registry
        ),
        "providers.set_selected": lambda req, emit: handle_providers_set_selected(
            req, emit, config_path=config_path
        ),
    }


class AsyncBridge:
    """Dispatches each request as its own task so one slow handler blocks nothing else."""

    def __init__(
        self,
        outbound: OutboundStream,
        store: LocalStore | None = None,
        config: AppConfig | None = None,
        config_path: Path | None = None,
    ) -> None:
        self.outbound = outbound
        self.registry = TaskRegistry()
        self.handlers: dict[str, Handler] = dict(DEFAULT_HANDLERS)
        if store is not None:
            self.handlers.update(meeting_handlers(store))
        if config is not None and config_path is not None:
            self.handlers.update(
                chat_handlers(config, config_path, self.registry, ProviderRegistry())
            )
        self._running: dict[str, asyncio.Event] = {}

    def dispatch(self, request: Request) -> asyncio.Task[None]:
        running = asyncio.Event()
        self._running[request.id] = running
        task = asyncio.create_task(self._run(request, running))
        self.registry.register(request, task)
        return task

    async def wait_until_running(self, request_id: str) -> None:
        await self._running[request_id].wait()

    async def _run(self, request: Request, running: asyncio.Event) -> None:
        handler = self.handlers.get(request.method)
        running.set()
        try:
            if handler is None:
                reply = _err_reply(
                    request.id,
                    ErrorCode.INVALID_REQUEST,
                    f"unknown method: {request.method}",
                )
            else:
                reply = await handler(request, self.outbound.send)
        except asyncio.CancelledError:
            await self._finish_cancelled(request)
        except Exception as exc:
            reply = _err_reply(request.id, ErrorCode.INTERNAL, f"{type(exc).__name__}: {exc}")
            await self.outbound.send(reply)
        else:
            await self.outbound.send(reply)
        finally:
            self.registry.forget(request)
            self._running.pop(request.id, None)

    async def _finish_cancelled(self, request: Request) -> None:
        """Cancellation is a terminal state, not a failure: signal it on both channels.

        The event can be dropped by the host's bounded channel (docs/architecture/01-ipc.md),
        so the reply carries the same outcome.
        """
        outcome = asyncio.gather(
            self.outbound.send(stream_event(request.id, CANCELLED_KIND)),
            self.outbound.send(Reply(id=request.id, result={"cancelled": True})),
        )
        shielded = asyncio.shield(outcome)
        try:
            await shielded
        except asyncio.CancelledError:
            await outcome

    async def drain(self) -> None:
        self.registry.cancel_all()
        pending = [task for task in self.registry.tasks() if not task.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


def parse_line(line: str) -> Request | Reply:
    try:
        return Request.model_validate_json(line)
    except ValidationError as exc:
        try:
            parsed = json.loads(line)
            rid = parsed.get("id", "") if isinstance(parsed, dict) else ""
        except json.JSONDecodeError:
            rid = ""
        return _err_reply(rid, ErrorCode.PARSE_ERROR, str(exc))


async def read_line(stdin: TextIO) -> str:
    """Read one line off the event loop so in-flight handlers keep running.

    Iterating a blocking stream directly would stall every task until the next
    byte arrives, which is invisible to StringIO tests and fatal over a pipe.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, stdin.readline)


async def serve(
    stdin: TextIO,
    stdout: TextIO,
    *,
    store: LocalStore | None = None,
    config: AppConfig | None = None,
    config_path: Path | None = None,
) -> None:
    bridge = AsyncBridge(OutboundStream(stdout), store=store, config=config, config_path=config_path)
    if store is not None:
        from .meetings.session import recover_orphans

        await recover_orphans(store, bridge.outbound.send)
    while True:
        raw = await read_line(stdin)
        if not raw:
            break
        line = raw.strip()
        if not line:
            continue
        parsed = parse_line(line)
        if isinstance(parsed, Reply):
            await bridge.outbound.send(parsed)
            continue
        bridge.dispatch(parsed)
    await bridge.drain()


def run(
    stdin: TextIO,
    stdout: TextIO,
    *,
    store: LocalStore | None = None,
    config: AppConfig | None = None,
    config_path: Path | None = None,
) -> None:
    asyncio.run(serve(stdin, stdout, store=store, config=config, config_path=config_path))
