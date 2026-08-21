from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..db import LocalStore
from ..llm import ChatMessage

MAX_CONTEXT_UTTERANCES = 20
MAX_CONTEXT_CHARS = 8000

SYSTEM_PROMPT = (
    "You are a meeting assistant. Answer the user's question using only the transcript context "
    "provided. Cite utterance IDs from the context window when relevant."
)

CONTEXT_BLOCK_TEMPLATE = (
    "Transcript context (most recent last; speaker, start_ms, text):\n{utterances}"
)


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    utterance_id: str = Field(min_length=1)
    speaker: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    text_preview: str = Field(min_length=1, max_length=240)


class AskState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: str = Field(min_length=1)
    meeting_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer: str = ""
    context_utterance_ids: list[str] = Field(default_factory=list)


def build_context(
    store: LocalStore,
    meeting_id: str,
    *,
    max_utterances: int = MAX_CONTEXT_UTTERANCES,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> list[dict]:
    full = store.get_full_meeting(meeting_id)
    utterances = full["utterances"]
    chosen: list[dict] = []
    budget = max_chars
    for utterance in reversed(utterances):
        if len(chosen) >= max_utterances:
            break
        text_len = len(utterance["text"])
        if budget - text_len < 0 and chosen:
            break
        chosen.append(utterance)
        budget -= text_len
    chosen.reverse()
    return chosen


def _format_utterance(utterance: dict) -> str:
    speaker = utterance["speaker"]
    start_ms = int(utterance["start_ms"])
    text = utterance["text"]
    return f"[{speaker} @ {start_ms}ms] {text}"


def _format_context(utterances: list[dict], *, truncated: bool) -> str:
    if not utterances:
        return ""
    lines = [_format_utterance(u) for u in utterances]
    if truncated:
        lines.append("... (context truncated)")
    return CONTEXT_BLOCK_TEMPLATE.format(utterances="\n".join(lines))


def build_prompt(
    state: AskState,
    utterances: list[dict],
    *,
    truncated: bool = False,
) -> list[ChatMessage]:
    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
    ]
    context_block = _format_context(utterances, truncated=truncated)
    if context_block:
        messages.append(ChatMessage(role="system", content=context_block))
    messages.append(ChatMessage(role="user", content=state.question))
    return messages
