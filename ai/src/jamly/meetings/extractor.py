from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import Any, Literal, Protocol, Self

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..config import AppConfig
from ..db import LocalStore, StoreError
from ..llm import build_chat_model
from ..protocol import Event

UNKNOWN_SOURCE = "UNKNOWN"

FOLLOWUP_EMIT = "followup.emit"
FOLLOWUP_KINDS = ("question", "contradiction", "action", "todo")

MAX_TRANSCRIPT_UTTERANCES = 400
MAX_TRANSCRIPT_CHARS = 24000
MAX_REPAIR_ATTEMPTS = 3
MAX_ITEMS = 20
MAX_EVIDENCE_IDS = 3
MAX_ENUM_IDS = 150
TEXT_PREVIEW_LEN = 240

STRUCTURED_METHOD = "json_schema"

FOLLOWUP_SYSTEM_PROMPT = (
    "You extract follow-ups from a meeting transcript. Use only the transcript provided. "
    "Classify each follow-up as question, contradiction, action, or todo. Cite the utterance "
    f'IDs shown in [brackets]. If nothing in the transcript supports an item, cite ["{UNKNOWN_SOURCE}"]. '
    "Never invent an utterance ID."
)

REPAIR_PROMPT = (
    "That output failed validation:\n{error}\n"
    "Re-emit the whole object, corrected. Change nothing else."
)

TRANSCRIPT_BLOCK_TEMPLATE = (
    "Transcript (oldest first; [utterance_id] speaker@start_ms: text):\n{lines}"
)

FollowUpKind = Literal["question", "contradiction", "action", "todo"]

ModelFactory = Callable[..., BaseChatModel]
Emit = Callable[[Event], Awaitable[None]]


class StructuredRunnable(Protocol):
    async def ainvoke(self, messages: list[Any]) -> dict[str, Any]: ...


class Grounded(Protocol):
    body: str
    source_utterance_ids: list[str]


class EvidencedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    body: str = Field(min_length=1, max_length=400)
    source_utterance_ids: list[str] = Field(min_length=1, max_length=MAX_EVIDENCE_IDS)

    @model_validator(mode="after")
    def _unknown_source_is_exclusive(self) -> Self:
        if UNKNOWN_SOURCE in self.source_utterance_ids and len(self.source_utterance_ids) > 1:
            raise ValueError(f"{UNKNOWN_SOURCE} must be the only cited source")
        return self


class ActionItem(EvidencedItem):
    owner: str = ""


class ActionItems(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ActionItem] = Field(default_factory=list, max_length=MAX_ITEMS)


class FollowUp(EvidencedItem):
    kind: FollowUpKind
    ts_ms: int = Field(default=0, ge=0)


class FollowUps(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FollowUp] = Field(default_factory=list, max_length=MAX_ITEMS)


class FollowUpOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    followups: list[FollowUp] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def build_transcript(
    store: LocalStore,
    meeting_id: str,
    *,
    max_utterances: int = MAX_TRANSCRIPT_UTTERANCES,
    max_chars: int = MAX_TRANSCRIPT_CHARS,
) -> list[dict[str, Any]]:
    utterances = store.get_full_meeting(meeting_id)["utterances"]
    selected: list[dict[str, Any]] = []
    used = 0
    for utterance in reversed(utterances):
        text = str(utterance.get("text", ""))
        if len(selected) >= max_utterances or used + len(text) > max_chars:
            break
        selected.append(utterance)
        used += len(text)
    selected.reverse()
    return selected


def valid_utterance_ids(utterances: Iterable[dict[str, Any]]) -> set[str]:
    return {str(utterance["id"]) for utterance in utterances}


def utterance_start_ms(utterances: Iterable[dict[str, Any]]) -> dict[str, int]:
    return {str(utterance["id"]): int(utterance["start_ms"]) for utterance in utterances}


def format_transcript(utterances: Sequence[dict[str, Any]]) -> str:
    lines = "\n".join(
        f"[{utterance['id']}] {utterance['speaker']}@{utterance['start_ms']}ms: "
        f"{str(utterance['text'])[:TEXT_PREVIEW_LEN]}"
        for utterance in utterances
    )
    return TRANSCRIPT_BLOCK_TEMPLATE.format(lines=lines)


def evidence_enum(valid_ids: Sequence[str]) -> list[str]:
    return [*sorted(valid_ids), UNKNOWN_SOURCE]


def evidence_property(valid_ids: Sequence[str]) -> dict[str, Any]:
    item: dict[str, Any] = {"type": "string"}
    if len(valid_ids) <= MAX_ENUM_IDS:
        item["enum"] = evidence_enum(valid_ids)
    return {
        "type": "array",
        "minItems": 1,
        "maxItems": MAX_EVIDENCE_IDS,
        "items": item,
        "description": (
            "Utterance IDs from the [brackets] in the transcript that support this item. "
            f'If none apply, return exactly ["{UNKNOWN_SOURCE}"].'
        ),
    }


def action_item_properties(valid_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "body": {"type": "string"},
        "owner": {"type": "string", "description": "Owner name, or an empty string if unassigned."},
        "source_utterance_ids": evidence_property(valid_ids),
    }


def followups_schema(valid_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "title": "FollowUps",
        "description": "Follow-ups grounded in transcript utterances.",
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "maxItems": MAX_ITEMS,
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": list(FOLLOWUP_KINDS)},
                        "body": {"type": "string"},
                        "source_utterance_ids": evidence_property(valid_ids),
                    },
                    "required": ["kind", "body", "source_utterance_ids"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def bind_structured(model: BaseChatModel, schema: dict[str, Any]) -> StructuredRunnable:
    runnable = model.with_structured_output(schema, method=STRUCTURED_METHOD, include_raw=True)
    return runnable


async def structured_call(
    structured: StructuredRunnable,
    messages: list[Any],
    *,
    max_attempts: int = MAX_REPAIR_ATTEMPTS,
) -> tuple[dict[str, Any] | None, list[str]]:
    failures: list[str] = []
    conversation = list(messages)
    for _ in range(max_attempts):
        outcome = await structured.ainvoke(conversation)
        parsed = outcome.get("parsed")
        error = outcome.get("parsing_error")
        if parsed is not None and error is None:
            return dict(parsed), failures
        reason = str(error) if error is not None else "model returned no parsed object"
        failures.append(reason)
        conversation = [
            *messages,
            HumanMessage(content=REPAIR_PROMPT.format(error=reason)),
        ]
    return None, failures


def ground_items[GroundedT: Grounded](
    items: Sequence[GroundedT],
    valid_ids: set[str],
) -> tuple[list[GroundedT], list[str]]:
    kept: list[GroundedT] = []
    dropped: list[str] = []
    for item in items:
        if item.source_utterance_ids == [UNKNOWN_SOURCE]:
            dropped.append(f"{item.body!r}: unsupported, model cited {UNKNOWN_SOURCE}")
            continue
        bogus = sorted(set(item.source_utterance_ids) - valid_ids)
        if bogus:
            dropped.append(f"{item.body!r}: ungrounded utterance ids {bogus}")
            continue
        kept.append(item)
    return kept, dropped


def stamp_followups(
    followups: Sequence[FollowUp],
    start_ms_index: dict[str, int],
) -> list[FollowUp]:
    stamped: list[FollowUp] = []
    for followup in followups:
        offsets = [
            start_ms_index[identifier]
            for identifier in followup.source_utterance_ids
            if identifier in start_ms_index
        ]
        stamped.append(followup.model_copy(update={"ts_ms": min(offsets) if offsets else 0}))
    return stamped


def followup_event(followup: FollowUp, *, meeting_id: str) -> Event:
    return Event(
        method=FOLLOWUP_EMIT,
        params={
            "meeting_id": meeting_id,
            "kind": followup.kind,
            "body": followup.body,
            "ts_ms": followup.ts_ms,
            "citations": list(followup.source_utterance_ids),
        },
    )


def build_followup_messages(transcript_block: str) -> list[BaseMessage]:
    return [SystemMessage(content=FOLLOWUP_SYSTEM_PROMPT), HumanMessage(content=transcript_block)]


async def extract_followups(
    transcript: Sequence[dict[str, Any]],
    *,
    model_factory: ModelFactory = build_chat_model,
    config: AppConfig | None = None,
    max_attempts: int = MAX_REPAIR_ATTEMPTS,
) -> FollowUpOutcome:
    if not transcript:
        return FollowUpOutcome()

    settings = config or AppConfig()
    valid_ids = valid_utterance_ids(transcript)
    schema = followups_schema(sorted(valid_ids))
    messages = build_followup_messages(format_transcript(transcript))

    try:
        model = model_factory(settings.ai_provider, model_name=settings.ai_model)
        structured = bind_structured(model, schema)
        parsed, failures = await structured_call(structured, messages, max_attempts=max_attempts)
    except Exception as error:
        return FollowUpOutcome(errors=[f"followups: {type(error).__name__}: {error}"])

    if parsed is None:
        return FollowUpOutcome(errors=[f"followups: {failures[-1]}"] if failures else [])

    try:
        followups = FollowUps.model_validate(parsed).items
    except ValidationError as error:
        return FollowUpOutcome(errors=[f"followups: {error}"])

    kept, dropped = ground_items(followups, valid_ids)
    return FollowUpOutcome(
        followups=stamp_followups(kept, utterance_start_ms(transcript)),
        dropped=dropped,
    )


async def extract_followups_for_meeting(
    store: LocalStore,
    meeting_id: str,
    *,
    model_factory: ModelFactory = build_chat_model,
    config: AppConfig | None = None,
    max_attempts: int = MAX_REPAIR_ATTEMPTS,
) -> FollowUpOutcome:
    try:
        transcript = build_transcript(store, meeting_id)
    except StoreError as error:
        return FollowUpOutcome(errors=[f"followups: {error}"])
    return await extract_followups(
        transcript,
        model_factory=model_factory,
        config=config,
        max_attempts=max_attempts,
    )
