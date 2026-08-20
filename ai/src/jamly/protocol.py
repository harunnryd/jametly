from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    model_config = ConfigDict(extra="forbid")

    id: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    """Fire-and-forget notification. Never correlated, never replied to."""

    model_config = ConfigDict(extra="forbid")

    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class ErrorBody(BaseModel):
    """Error payload inside `Reply.error`."""

    code: ErrorCode
    message: str
    retryable: bool = False


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    result: Any | None = None
    error: ErrorBody | None = None

    @model_validator(mode="after")
    def _exactly_one_payload(self) -> Reply:
        if self.result is not None and self.error is not None:
            raise ValueError("reply carries both `result` and `error`; exactly one is allowed")
        return self

    def kind(self) -> Literal["ok", "err"]:
        return "ok" if self.error is None else "err"
