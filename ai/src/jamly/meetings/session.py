from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from pydantic import BaseModel, ConfigDict

from ..db import LocalStore, StoreError
from ..protocol import ErrorBody, ErrorCode, Event, Reply, Request

Emit = Callable[[Event], Awaitable[None]]

MEETING_ENDED = "meeting.ended"

MAX_TITLE_LEN = 200
MAX_SEARCH_LEN = 200


class CheckpointPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    segment_id: str = ""


def _err_reply(req_id: str, code: ErrorCode, message: str, retryable: bool = False) -> Reply:
    return Reply(id=req_id, error=ErrorBody(code=code, message=message, retryable=retryable))


def _meeting_ended(meeting_id: str) -> Event:
    return Event(
        method=MEETING_ENDED,
        params={
            "meeting_id": meeting_id,
            "summary_path": None,
            "export_paths": [],
        },
    )


async def _emit_meeting_ended(emit, meeting_id: str) -> None:
    event = _meeting_ended(meeting_id)
    outcome = asyncio.gather(emit(event))
    shielded = asyncio.shield(outcome)
    try:
        await shielded
    except asyncio.CancelledError:
        await outcome


async def handle_meeting_start(
    request: Request,
    emit: Emit,
    *,
    store: LocalStore,
) -> Reply:
    title_raw = request.params.get("title", "")
    if not isinstance(title_raw, str):
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, "`title` must be a string")
    title = title_raw[:MAX_TITLE_LEN]

    active = store.get_active_meeting()
    if active is not None:
        return _err_reply(
            request.id,
            ErrorCode.INVALID_REQUEST,
            "an active meeting is already in progress; stop it first",
        )

    meeting_id = store.create_meeting(title=title)
    return Reply(id=request.id, result={"meeting_id": meeting_id})


async def handle_meeting_stop(
    request: Request,
    emit: Emit,
    *,
    store: LocalStore,
) -> Reply:
    meeting_id = request.params.get("meeting_id")
    if not isinstance(meeting_id, str) or not meeting_id:
        return _err_reply(
            request.id, ErrorCode.INVALID_REQUEST, "`meeting_id` must be a non-empty string"
        )

    try:
        won = store.end_meeting(meeting_id)
    except StoreError:
        return _err_reply(request.id, ErrorCode.MEETING_NOT_FOUND, "meeting not found")

    if won:
        await _emit_meeting_ended(emit, meeting_id)
    return Reply(id=request.id, result={"already_ended": not won})


async def handle_meeting_list(
    request: Request,
    emit: Emit,
    *,
    store: LocalStore,
) -> Reply:
    params = request.params
    raw_limit = params.get("limit", 20)
    if isinstance(raw_limit, bool) or not isinstance(raw_limit, int) or raw_limit < 1:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, "`limit` must be a positive integer")

    search_raw = params.get("search")
    search: str | None = None
    if search_raw is not None:
        if not isinstance(search_raw, str):
            return _err_reply(
                request.id, ErrorCode.INVALID_REQUEST, "`search` must be a string"
            )
        search = search_raw[:MAX_SEARCH_LEN]

    payload = store.list_meetings(limit=raw_limit, search=search)
    return Reply(id=request.id, result=payload)


async def handle_meeting_get(
    request: Request,
    emit: Emit,
    *,
    store: LocalStore,
) -> Reply:
    meeting_id = request.params.get("meeting_id")
    if not isinstance(meeting_id, str) or not meeting_id:
        return _err_reply(
            request.id, ErrorCode.INVALID_REQUEST, "`meeting_id` must be a non-empty string"
        )

    try:
        payload = store.get_full_meeting(meeting_id)
    except StoreError:
        return _err_reply(request.id, ErrorCode.MEETING_NOT_FOUND, "meeting not found")

    return Reply(id=request.id, result=payload)


async def recover_orphans(store: LocalStore, emit) -> None:
    orphans = store.find_orphans()
    for row in orphans:
        meeting_id = row["id"]
        try:
            store.save_checkpoint(
                meeting_id, CheckpointPayload(status="recovered_on_cold_start")
            )
        except StoreError:
            continue
