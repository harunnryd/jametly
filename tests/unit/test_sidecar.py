from __future__ import annotations

import io
import json

import pytest
from pydantic import ValidationError

from jamly.__main__ import REGISTRY, _handle, _serve
from jamly.protocol import ErrorBody, ErrorCode, Event, Reply, Request


def test_handle_echo() -> None:
    reply = _handle(Request(id="r1", method="echo", params={"x": "hi"}))

    assert reply.id == "r1"
    assert reply.result == {"x": "hi"}
    assert reply.error is None


def test_handle_unknown_method() -> None:
    reply = _handle(Request(id="r2", method="unknown", params={}))

    assert reply.id == "r2"
    assert reply.result is None
    assert reply.error is not None
    assert reply.error.code is ErrorCode.INVALID_REQUEST


def test_serve_handles_ndjson_stream() -> None:
    stdin = io.StringIO(
        '\n'.join(
            [
                "",
                '{"id":"r1","method":"echo","params":{"x":"hi"}}',
                '{"id":"r2","method":"unknown","params":{}}',
                '{"id":"r3","method":"echo","unexpected":true}',
                "not json",
            ]
        )
        + "\n"
    )
    stdout = io.StringIO()

    _serve(stdin, stdout)

    replies = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert replies[0] == {"id": "r1", "result": {"x": "hi"}}
    assert replies[1]["id"] == "r2"
    assert replies[1]["error"]["code"] == "INVALID_REQUEST"
    assert replies[2]["id"] == "r3"
    assert replies[2]["error"]["code"] == "PARSE_ERROR"
    assert replies[3]["id"] == ""
    assert replies[3]["error"]["code"] == "PARSE_ERROR"


def test_registry_routes_known_methods() -> None:
    assert set(REGISTRY) == {"echo", "debug.stream"}


def test_registry_dispatch_is_the_only_route_to_a_handler() -> None:
    reply = REGISTRY["echo"](Request(id="r1", method="echo", params={"x": "hi"}), lambda _e: None)

    assert reply.result == {"x": "hi"}


def test_handle_debug_stream_emits_ordered_events_then_reply() -> None:
    emitted: list[Event] = []

    reply = _handle(Request(id="r1", method="debug.stream", params={"count": 2}), emitted.append)

    assert [e.method for e in emitted] == ["stream.event"] * 3
    assert [e.params["kind"] for e in emitted] == ["token", "token", "done"]
    assert {e.params["correlation_id"] for e in emitted} == {"r1"}
    assert reply.id == "r1"
    assert reply.result == {"count": 2}
    assert reply.error is None


def test_handle_debug_stream_defaults_to_one_token() -> None:
    emitted: list[Event] = []

    _handle(Request(id="r1", method="debug.stream", params={}), emitted.append)

    assert [e.params["kind"] for e in emitted] == ["token", "done"]


@pytest.mark.parametrize("count", [-1, "two", 1.5, None])
def test_handle_debug_stream_rejects_bad_count(count: object) -> None:
    emitted: list[Event] = []

    reply = _handle(Request(id="r1", method="debug.stream", params={"count": count}), emitted.append)

    assert emitted == []
    assert reply.error is not None
    assert reply.error.code is ErrorCode.INVALID_REQUEST


def test_handle_unknown_method_emits_nothing() -> None:
    emitted: list[Event] = []

    reply = _handle(Request(id="r2", method="nope", params={}), emitted.append)

    assert emitted == []
    assert reply.error is not None
    assert reply.error.code is ErrorCode.INVALID_REQUEST


def test_reply_rejects_both_result_and_error() -> None:
    with pytest.raises(ValidationError):
        Reply(
            id="r1",
            result={"x": 1},
            error=ErrorBody(code=ErrorCode.INTERNAL, message="boom"),
        )


def test_reply_accepts_exactly_one_of_result_or_error() -> None:
    assert Reply(id="r1", result={"x": 1}).kind() == "ok"
    assert Reply(id="r1", error=ErrorBody(code=ErrorCode.INTERNAL, message="boom")).kind() == "err"


def test_event_serializes_without_an_id() -> None:
    ev = Event(method="stream.event", params={"correlation_id": "r1", "kind": "done"})

    assert json.loads(ev.model_dump_json(exclude_none=True)) == {
        "method": "stream.event",
        "params": {"correlation_id": "r1", "kind": "done"},
    }


def test_event_forbids_an_id_field() -> None:
    with pytest.raises(ValidationError):
        Event(method="stream.event", params={}, id="r1")  # type: ignore[call-arg]


def test_serve_writes_events_before_the_correlated_reply() -> None:
    stdin = io.StringIO('{"id":"r1","method":"debug.stream","params":{"count":2}}\n')
    stdout = io.StringIO()

    _serve(stdin, stdout)

    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert [line.get("method") for line in lines[:3]] == ["stream.event"] * 3
    assert [line["params"]["kind"] for line in lines[:3]] == ["token", "token", "done"]
    assert lines[3] == {"id": "r1", "result": {"count": 2}}
