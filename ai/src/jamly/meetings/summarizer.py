from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config import AppConfig
from ..db import LocalStore, StoreError
from ..llm import build_chat_model
from .extractor import (
    MAX_ITEMS,
    MAX_REPAIR_ATTEMPTS,
    UNKNOWN_SOURCE,
    ActionItem,
    EvidencedItem,
    ModelFactory,
    action_item_properties,
    bind_structured,
    build_transcript,
    evidence_property,
    format_transcript,
    ground_items,
    structured_call,
    valid_utterance_ids,
)

SUMMARY_SYSTEM_PROMPT = (
    "You summarize a meeting transcript. Use only the transcript provided. Record decisions the "
    "participants actually made, risks they raised, questions left open, and action items they "
    "committed to. Cite the utterance IDs shown in [brackets] for every entry. If nothing in the "
    f'transcript supports an entry, cite ["{UNKNOWN_SOURCE}"]. Never invent an utterance ID, and '
    "never record an action item nobody committed to."
)

SUMMARY_SECTIONS = ("decisions", "risks", "questions")


class SummaryPoint(EvidencedItem):
    pass


class MeetingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meeting_id: str = Field(min_length=1)
    decisions: list[SummaryPoint] = Field(default_factory=list)
    risks: list[SummaryPoint] = Field(default_factory=list)
    questions: list[SummaryPoint] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)


class SummaryOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: MeetingSummary
    dropped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def summary_schema(valid_ids: Sequence[str]) -> dict[str, Any]:
    section = {
        "type": "array",
        "maxItems": MAX_ITEMS,
        "items": {
            "type": "object",
            "properties": {
                "body": {"type": "string"},
                "source_utterance_ids": evidence_property(valid_ids),
            },
            "required": ["body", "source_utterance_ids"],
            "additionalProperties": False,
        },
    }
    return {
        "title": "MeetingSummary",
        "description": "A meeting summary grounded in transcript utterances.",
        "type": "object",
        "properties": {
            **{name: dict(section) for name in SUMMARY_SECTIONS},
            "action_items": {
                "type": "array",
                "maxItems": MAX_ITEMS,
                "items": {
                    "type": "object",
                    "properties": action_item_properties(valid_ids),
                    "required": ["body", "owner", "source_utterance_ids"],
                    "additionalProperties": False,
                },
            },
        },
        "required": [*SUMMARY_SECTIONS, "action_items"],
        "additionalProperties": False,
    }


def build_summary_messages(transcript_block: str) -> list[BaseMessage]:
    return [SystemMessage(content=SUMMARY_SYSTEM_PROMPT), HumanMessage(content=transcript_block)]


async def summarize_transcript(
    transcript: Sequence[dict[str, Any]],
    meeting_id: str,
    *,
    model_factory: ModelFactory = build_chat_model,
    config: AppConfig | None = None,
    max_attempts: int = MAX_REPAIR_ATTEMPTS,
) -> SummaryOutcome:
    empty = MeetingSummary(meeting_id=meeting_id)
    if not transcript:
        return SummaryOutcome(summary=empty)

    settings = config or AppConfig()
    valid_ids = valid_utterance_ids(transcript)
    schema = summary_schema(sorted(valid_ids))
    messages = build_summary_messages(format_transcript(transcript))

    try:
        model = model_factory(settings.ai_provider, model_name=settings.ai_model)
        structured = bind_structured(model, schema)
        parsed, failures = await structured_call(structured, messages, max_attempts=max_attempts)
    except Exception as error:
        return SummaryOutcome(summary=empty, errors=[f"summary: {type(error).__name__}: {error}"])

    if parsed is None:
        return SummaryOutcome(
            summary=empty, errors=[f"summary: {failures[-1]}"] if failures else []
        )

    try:
        summary = MeetingSummary.model_validate({**parsed, "meeting_id": meeting_id})
    except ValidationError as error:
        return SummaryOutcome(summary=empty, errors=[f"summary: {error}"])

    dropped: list[str] = []
    grounded: dict[str, Any] = {"meeting_id": meeting_id}
    for name in SUMMARY_SECTIONS:
        kept, section_dropped = ground_items(getattr(summary, name), valid_ids)
        grounded[name] = kept
        dropped.extend(f"{name}: {reason}" for reason in section_dropped)
    kept_actions, actions_dropped = ground_items(summary.action_items, valid_ids)
    grounded["action_items"] = kept_actions
    dropped.extend(f"action_items: {reason}" for reason in actions_dropped)

    return SummaryOutcome(summary=MeetingSummary(**grounded), dropped=dropped)


async def summarize_meeting(
    store: LocalStore,
    meeting_id: str,
    *,
    model_factory: ModelFactory = build_chat_model,
    config: AppConfig | None = None,
    max_attempts: int = MAX_REPAIR_ATTEMPTS,
) -> SummaryOutcome:
    try:
        transcript = build_transcript(store, meeting_id)
    except StoreError as error:
        return SummaryOutcome(
            summary=MeetingSummary(meeting_id=meeting_id), errors=[f"summary: {error}"]
        )
    return await summarize_transcript(
        transcript,
        meeting_id,
        model_factory=model_factory,
        config=config,
        max_attempts=max_attempts,
    )
