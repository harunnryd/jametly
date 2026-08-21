from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
