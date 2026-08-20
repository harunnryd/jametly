from __future__ import annotations

import json
import sys
from typing import Callable, TextIO

from pydantic import ValidationError

from .protocol import ErrorBody, ErrorCode, Event, Reply, Request

Emit = Callable[[Event], None]
Handler = Callable[[Request, Emit], Reply]

STREAM_EVENT = "stream.event"
DEFAULT_STREAM_COUNT = 1


def _err_reply(req_id: str, code: ErrorCode, message: str, retryable: bool = False) -> Reply:
    return Reply(id=req_id, error=ErrorBody(code=code, message=message, retryable=retryable))


def _discard(_event: Event) -> None:
    return None


def _handle_echo(req: Request, emit: Emit) -> Reply:
    return Reply(id=req.id, result=req.params)


def _stream_count(params: dict[str, object]) -> int:
    count = params.get("count", DEFAULT_STREAM_COUNT)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"`count` must be a non-negative integer, got {count!r}")
    return count


def _handle_debug_stream(req: Request, emit: Emit) -> Reply:
    try:
        count = _stream_count(req.params)
    except ValueError as exc:
        return _err_reply(req.id, ErrorCode.INVALID_REQUEST, str(exc))

    for index in range(count):
        emit(
            Event(
                method=STREAM_EVENT,
                params={
                    "correlation_id": req.id,
                    "kind": "token",
                    "data": str(index),
                },
            )
        )
    emit(Event(method=STREAM_EVENT, params={"correlation_id": req.id, "kind": "done"}))
    return Reply(id=req.id, result={"count": count})


REGISTRY: dict[str, Handler] = {
    "echo": _handle_echo,
    "debug.stream": _handle_debug_stream,
}


def _handle(req: Request, emit: Emit = _discard) -> Reply:
    handler = REGISTRY.get(req.method)
    if handler is None:
        return _err_reply(req.id, ErrorCode.INVALID_REQUEST, f"unknown method: {req.method}")
    return handler(req, emit)


def _serve(stdin: TextIO, stdout: TextIO) -> None:
    def emit(event: Event) -> None:
        stdout.write(event.model_dump_json(exclude_none=True) + "\n")
        stdout.flush()

    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = Request.model_validate_json(line)
        except ValidationError as exc:
            try:
                parsed = json.loads(line)
                rid = parsed.get("id", "") if isinstance(parsed, dict) else ""
            except json.JSONDecodeError:
                rid = ""
            reply = _err_reply(rid, ErrorCode.PARSE_ERROR, str(exc))
        except json.JSONDecodeError as exc:
            reply = _err_reply("", ErrorCode.PARSE_ERROR, f"invalid JSON: {exc}")
        else:
            reply = _handle(req, emit)

        stdout.write(reply.model_dump_json(exclude_none=True) + "\n")
        stdout.flush()


def main() -> None:
    _serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
