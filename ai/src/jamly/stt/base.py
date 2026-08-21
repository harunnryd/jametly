"""Speech-to-text provider contract and the partial/final transcript events it produces.

Not the place for decoding or audio handling: providers own model access only, and
`jamly.audio` owns ingest, gating, and orchestration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

PARTIAL_EVENT = "transcript.partial"
FINAL_EVENT = "transcript.final"

Speaker = Literal["A", "B"]


class SttError(Exception):
    """A safe, user-facing speech-to-text error that never carries audio or model paths."""


class SegmentPart(BaseModel):
    """One step of a provider's progress through a single voiced segment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    final: bool
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class PartialTranscript(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    speaker: Speaker
    text: str
    segment_id: str


class FinalTranscript(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    speaker: Speaker
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    segment_id: str

    @model_validator(mode="after")
    def _ordered_span(self) -> FinalTranscript:
        if self.end_ms < self.start_ms:
            raise ValueError("`end_ms` precedes `start_ms`")
        return self


class STTProvider(ABC):
    """A speech-to-text backend whose model loads on first use, never at construction."""

    def __init__(self) -> None:
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self._load()
            self._loaded = True

    @abstractmethod
    def _load(self) -> None: ...

    @abstractmethod
    def transcribe(
        self, pcm: NDArray[np.float32], *, language: str | None = None
    ) -> Iterator[SegmentPart]:
        """Yield cumulative partials for one voiced segment, then exactly one final part."""
