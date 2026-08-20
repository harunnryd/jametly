from __future__ import annotations

import asyncio
import io
import json

import pytest

from jamly.bridge import (
    CANCELLED_KIND,
    STREAM_EVENT,
    AsyncBridge,
    OutboundStream,
    TaskRegistry,
    serve,
)
from jamly.protocol import Event, Reply, Request


def _lines(stdout: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


async def test_echo_round_trips_over_the_async_runtime() -> None:
    stdout = io.StringIO()

    await serve(io.StringIO('{"id":"r1","method":"echo","params":{"x":"hi"}}\n'), stdout)

    assert _lines(stdout) == [{"id": "r1", "result": {"x": "hi"}}]


async def test_debug_stream_keeps_the_jam_0002_wire_shape() -> None:
    stdout = io.StringIO()

    await serve(io.StringIO('{"id":"r1","method":"debug.stream","params":{"count":2}}\n'), stdout)

    lines = _lines(stdout)
    assert [line.get("method") for line in lines[:3]] == [STREAM_EVENT] * 3
    assert [line["params"]["kind"] for line in lines[:3]] == ["token", "token", "done"]
    assert all("id" not in line for line in lines[:3])
    assert lines[3] == {"id": "r1", "result": {"count": 2}}


async def test_unknown_method_still_returns_invalid_request() -> None:
    stdout = io.StringIO()

    await serve(io.StringIO('{"id":"r1","method":"nope","params":{}}\n'), stdout)

    assert _lines(stdout)[0]["error"]["code"] == "INVALID_REQUEST"


async def test_malformed_line_returns_parse_error_with_empty_id() -> None:
    stdout = io.StringIO()

    await serve(io.StringIO("not json\n"), stdout)

    reply = _lines(stdout)[0]
    assert reply["id"] == ""
    assert reply["error"]["code"] == "PARSE_ERROR"


async def test_eof_drains_without_pending_work() -> None:
    stdout = io.StringIO()

    await asyncio.wait_for(serve(io.StringIO(""), stdout), timeout=5)

    assert stdout.getvalue() == ""


async def test_outbound_stream_serializes_concurrent_writers() -> None:
    stdout = io.StringIO()
    outbound = OutboundStream(stdout)
    payload = {"correlation_id": "r1", "kind": "token", "data": "x" * 200}

    await asyncio.gather(
        *(outbound.send(Event(method=STREAM_EVENT, params=payload)) for _ in range(50))
    )

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 50
    for line in lines:
        assert json.loads(line)["params"]["data"] == "x" * 200


async def test_registry_cancels_by_request_id() -> None:
    registry = TaskRegistry()
    started = asyncio.Event()

    async def forever() -> None:
        started.set()
        await asyncio.sleep(3600)

    task = asyncio.create_task(forever())
    registry.register(Request(id="r1", method="debug.sleep", params={}), task)
    await started.wait()

    assert registry.cancel("r1") is True
    with pytest.raises(asyncio.CancelledError):
        await task
    assert registry.cancel("r1") is False


async def test_registry_cancels_every_request_for_a_thread() -> None:
    registry = TaskRegistry()
    tasks = []
    for index in range(3):
        task = asyncio.create_task(asyncio.sleep(3600))
        tasks.append(task)
        registry.register(
            Request(id=f"r{index}", method="debug.sleep", params={"thread_id": "t-1"}),
            task,
        )
    other = asyncio.create_task(asyncio.sleep(3600))
    registry.register(Request(id="r9", method="debug.sleep", params={"thread_id": "t-2"}), other)

    assert registry.cancel_thread("t-1") == 3

    for task in tasks:
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not other.done()
    other.cancel()


async def test_registry_forget_clears_the_thread_index() -> None:
    registry = TaskRegistry()
    task = asyncio.create_task(asyncio.sleep(0))
    request = Request(id="r1", method="debug.sleep", params={"thread_id": "t-1"})
    registry.register(request, task)

    registry.forget(request)

    assert registry.cancel_thread("t-1") == 0
    assert registry.in_flight() == 0
    await task


async def test_cancelled_handler_emits_terminal_event_and_reply() -> None:
    stdout = io.StringIO()
    bridge = AsyncBridge(OutboundStream(stdout))
    request = Request(id="r1", method="debug.sleep", params={"ms": 60_000})

    task = bridge.dispatch(request)
    await bridge.wait_until_running("r1")
    assert bridge.registry.cancel("r1") is True
    await task

    lines = _lines(stdout)
    assert lines[0]["method"] == STREAM_EVENT
    assert lines[0]["params"] == {"correlation_id": "r1", "kind": CANCELLED_KIND}
    assert lines[1] == {"id": "r1", "result": {"cancelled": True}}


async def test_cancellation_emits_exactly_one_terminal_signal() -> None:
    stdout = io.StringIO()
    bridge = AsyncBridge(OutboundStream(stdout))
    request = Request(id="r1", method="debug.sleep", params={"ms": 60_000})

    task = bridge.dispatch(request)
    await bridge.wait_until_running("r1")
    bridge.registry.cancel("r1")
    bridge.registry.cancel("r1")
    await task

    lines = _lines(stdout)
    terminal = [line for line in lines if line.get("params", {}).get("kind") == CANCELLED_KIND]
    replies = [line for line in lines if "id" in line]
    assert len(terminal) == 1
    assert len(replies) == 1


async def test_slow_handler_does_not_block_an_unrelated_request() -> None:
    stdout = io.StringIO()
    bridge = AsyncBridge(OutboundStream(stdout))

    slow = bridge.dispatch(Request(id="slow", method="debug.sleep", params={"ms": 60_000}))
    await bridge.wait_until_running("slow")

    await bridge.dispatch(Request(id="fast", method="echo", params={"x": 1}))

    assert _lines(stdout) == [{"id": "fast", "result": {"x": 1}}]
    assert bridge.registry.cancel("slow") is True
    await slow


async def test_concurrent_requests_correlate_to_their_own_replies() -> None:
    stdout = io.StringIO()
    bridge = AsyncBridge(OutboundStream(stdout))

    await asyncio.gather(
        *(
            bridge.dispatch(Request(id=f"r{index}", method="echo", params={"n": index}))
            for index in range(25)
        )
    )

    replies = {line["id"]: line["result"]["n"] for line in _lines(stdout)}
    assert replies == {f"r{index}": index for index in range(25)}


async def test_eof_cancels_in_flight_work_deterministically() -> None:
    stdout = io.StringIO()
    stdin = io.StringIO('{"id":"r1","method":"debug.sleep","params":{"ms":60000}}\n')

    await asyncio.wait_for(serve(stdin, stdout), timeout=5)

    lines = _lines(stdout)
    assert lines[0]["params"]["kind"] == CANCELLED_KIND
    assert lines[1] == {"id": "r1", "result": {"cancelled": True}}


async def test_debug_sleep_rejects_a_bad_duration() -> None:
    stdout = io.StringIO()

    await serve(io.StringIO('{"id":"r1","method":"debug.sleep","params":{"ms":-1}}\n'), stdout)

    assert _lines(stdout)[0]["error"]["code"] == "INVALID_REQUEST"


async def test_handler_exception_becomes_an_internal_error_reply() -> None:
    stdout = io.StringIO()
    bridge = AsyncBridge(OutboundStream(stdout))

    async def boom(request: Request, emit: object) -> Reply:
        raise RuntimeError("handler blew up")

    bridge.handlers["debug.boom"] = boom  # type: ignore[assignment]
    await bridge.dispatch(Request(id="r1", method="debug.boom", params={}))

    reply = _lines(stdout)[0]
    assert reply["id"] == "r1"
    assert reply["error"]["code"] == "INTERNAL"
