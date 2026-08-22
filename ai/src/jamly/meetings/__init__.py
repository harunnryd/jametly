from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..config import AppConfig
from ..db import LocalStore, StoreError
from ..llm import build_chat_model
from .extractor import (
    FOLLOWUP_EMIT,
    FOLLOWUP_KINDS,
    UNKNOWN_SOURCE,
    ActionItem,
    ActionItems,
    Emit,
    FollowUp,
    FollowUpOutcome,
    FollowUps,
    ModelFactory,
    build_transcript,
    extract_followups,
    followup_event,
)
from .session import (
    handle_meeting_get,
    handle_meeting_list,
    handle_meeting_start,
    handle_meeting_stop,
    recover_orphans,
)
from .summarizer import (
    MeetingSummary,
    SummaryOutcome,
    SummaryPoint,
    summarize_meeting,
    summarize_transcript,
)


class PostProcessResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: MeetingSummary
    followups: list[FollowUp] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


async def run_post_process(
    store: LocalStore,
    meeting_id: str,
    emit: Emit,
    *,
    model_factory: ModelFactory = build_chat_model,
    config: AppConfig | None = None,
) -> PostProcessResult:
    try:
        transcript = build_transcript(store, meeting_id)
    except StoreError as error:
        return PostProcessResult(
            summary=MeetingSummary(meeting_id=meeting_id), errors=[f"transcript: {error}"]
        )

    summary_outcome = await summarize_transcript(
        transcript, meeting_id, model_factory=model_factory, config=config
    )
    followup_outcome = await extract_followups(
        transcript, model_factory=model_factory, config=config
    )

    for followup in followup_outcome.followups:
        await emit(followup_event(followup, meeting_id=meeting_id))

    return PostProcessResult(
        summary=summary_outcome.summary,
        followups=followup_outcome.followups,
        dropped=[*summary_outcome.dropped, *followup_outcome.dropped],
        errors=[*summary_outcome.errors, *followup_outcome.errors],
    )


__all__ = [
    "FOLLOWUP_EMIT",
    "FOLLOWUP_KINDS",
    "UNKNOWN_SOURCE",
    "ActionItem",
    "ActionItems",
    "FollowUp",
    "FollowUpOutcome",
    "FollowUps",
    "MeetingSummary",
    "PostProcessResult",
    "SummaryOutcome",
    "SummaryPoint",
    "extract_followups",
    "followup_event",
    "handle_meeting_get",
    "handle_meeting_list",
    "handle_meeting_start",
    "handle_meeting_stop",
    "recover_orphans",
    "run_post_process",
    "summarize_meeting",
    "summarize_transcript",
]
