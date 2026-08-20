"""Wire-protocol mirrors of `core/ipc-proto/src/lib.rs` (Pydantic v2).

If you change these, change `core/ipc-proto/src/lib.rs` in lockstep.
The contract tests in `core/ipc-proto/tests/protocol_contract.rs` will
catch drift.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ErrorCode(StrEnum):
    PARSE_ERROR = "PARSE_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    IPC_SCHEMA_VERSION = "IPC_SCHEMA_VERSION"
    PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    PROVIDER_AUTH = "PROVIDER_AUTH"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PYTHON_TIMEOUT = "PYTHON_TIMEOUT"
    AUDIO_DEVICE_LOST = "AUDIO_DEVICE_LOST"
    OCR_FAILED = "OCR_FAILED"
    MEETING_NOT_FOUND = "MEETING_NOT_FOUND"
    INTERNAL = "INTERNAL"


class Request(BaseModel):
    """Rust → Python request envelope."""

    model_config = ConfigDict(extra="forbid")

    id: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class ErrorBody(BaseModel):
    """Error payload inside `Reply.error`."""

    code: ErrorCode
    message: str
    retryable: bool = False


class Reply(BaseModel):
    """Python → Rust reply envelope. Exactly one of `result` or `error`."""

    model_config = ConfigDict(extra="forbid")

    id: str
    result: Any | None = None
    error: ErrorBody | None = None

    def kind(self) -> Literal["ok", "err"]:
        return "ok" if self.error is None else "err"
