from __future__ import annotations

import io
import json

from jamly.__main__ import _handle, _serve
from jamly.protocol import ErrorCode, Request


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
