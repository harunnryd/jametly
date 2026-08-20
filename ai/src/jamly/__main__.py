"""jametly AI sidecar entry point.

Phase 0: single in-flight request at a time, lock-step request/reply
over stdio NDJSON. Phase 1+ adds the streaming event channel.

Wire protocol (matches `core/ipc-proto/src/lib.rs`):
- one request per line, JSON-encoded
- one reply per line, JSON-encoded (untagged ok-or-err)
- unknown methods return `INVALID_REQUEST`
- malformed JSON returns `PARSE_ERROR`
"""

from __future__ import annotations

import json
import sys

from pydantic import ValidationError

from .protocol import ErrorBody, ErrorCode, Reply, Request


def _err_reply(req_id: str, code: ErrorCode, message: str, retryable: bool = False) -> Reply:
    return Reply(id=req_id, error=ErrorBody(code=code, message=message, retryable=retryable))


def _handle(req: Request) -> Reply:
    if req.method == "echo":
        return Reply(id=req.id, result=req.params)
    return _err_reply(
        req.id,
        ErrorCode.INVALID_REQUEST,
        f"unknown method: {req.method}",
    )


def _serve(stdin, stdout) -> None:
    for line in stdin:
        line = line.strip()
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
            reply = _handle(req)

        stdout.write(reply.model_dump_json(exclude_none=True) + "\n")
        stdout.flush()


def main() -> None:
    _serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
