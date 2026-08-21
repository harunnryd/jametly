"""PCM ingest, chunking, voice-activity gating, and speech-to-text orchestration.

Not the place for model access: providers in `jamly.stt` own that, and this module
only decides which audio is worth handing them.
"""

from __future__ import annotations

import asyncio
import functools
import uuid
import wave
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import AppConfig
from .protocol import ErrorBody, ErrorCode, Event, Reply, Request
from .stt.base import (
    FinalTranscript,
    PartialTranscript,
    Speaker,
    SegmentPart,
    STTProvider,
    SttError,
)

BRIDGE_SAMPLE_RATE = 16_000
BRIDGE_CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
FULL_SCALE = 32_768.0

INGEST_FRAME_MS = 30
INGEST_FRAME_SAMPLES = BRIDGE_SAMPLE_RATE * INGEST_FRAME_MS // 1000

VAD_FRAME_SAMPLES = 512
VAD_FRAME_MS = VAD_FRAME_SAMPLES * 1000 // BRIDGE_SAMPLE_RATE

DEFAULT_HANGOVER_FRAMES = 3
DEFAULT_TRANSCRIBE_TIMEOUT_S = 120.0

Emit = Callable[[Event], Awaitable[None]]
IsSpeech = Callable[[NDArray[np.float32]], bool]
Transcript = PartialTranscript | FinalTranscript


class AudioError(Exception):
    """A safe, user-facing audio error that never carries samples or absolute paths."""


class VoicedSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    samples: tuple[int, ...]

    @model_validator(mode="after")
    def _ordered_span(self) -> VoicedSegment:
        if self.end_ms < self.start_ms:
            raise ValueError("`end_ms` precedes `start_ms`")
        return self


def duration_ms(
    sample_count: int, *, sample_rate: int = BRIDGE_SAMPLE_RATE, channels: int = BRIDGE_CHANNELS
) -> int:
    per_channel = sample_count // max(1, channels)
    return per_channel * 1000 // max(1, sample_rate)


def to_float32(samples: Sequence[int]) -> NDArray[np.float32]:
    raw = np.asarray(samples, dtype=np.float32) / FULL_SCALE
    return np.clip(raw, -1.0, 1.0).astype(np.float32)


def chunk_samples(
    samples: Sequence[int],
    max_ms: int,
    *,
    sample_rate: int = BRIDGE_SAMPLE_RATE,
    channels: int = BRIDGE_CHANNELS,
) -> list[tuple[int, ...]]:
    per_chunk = max(1, max(1, max_ms) * max(1, sample_rate) // 1000) * max(1, channels)
    return [
        tuple(samples[start : start + per_chunk]) for start in range(0, len(samples), per_chunk)
    ]


class VadGate:
    """Buffers a 30 ms ingest cadence into the exact 512-sample frames silero requires."""

    def __init__(
        self,
        is_speech: IsSpeech,
        *,
        hangover_frames: int = DEFAULT_HANGOVER_FRAMES,
        start_ms: int = 0,
    ) -> None:
        self._is_speech = is_speech
        self._hangover_frames = max(0, hangover_frames)
        self._origin_ms = start_ms
        self._pending: list[int] = []
        self._frames_seen = 0
        self._voiced: list[int] = []
        self._voiced_start_ms: int | None = None
        self._voiced_end_ms = 0
        self._silence_run = 0

    @property
    def pending_samples(self) -> int:
        return len(self._pending)

    def push(self, samples: Sequence[int]) -> list[VoicedSegment]:
        self._pending.extend(samples)
        closed: list[VoicedSegment] = []
        while len(self._pending) >= VAD_FRAME_SAMPLES:
            frame = self._pending[:VAD_FRAME_SAMPLES]
            del self._pending[:VAD_FRAME_SAMPLES]
            segment = self._consume(frame)
            if segment is not None:
                closed.append(segment)
        return closed

    def flush(self) -> list[VoicedSegment]:
        segment = self._close()
        return [] if segment is None else [segment]

    def _consume(self, frame: list[int]) -> VoicedSegment | None:
        start_ms = self._origin_ms + duration_ms(self._frames_seen * VAD_FRAME_SAMPLES)
        self._frames_seen += 1
        end_ms = self._origin_ms + duration_ms(self._frames_seen * VAD_FRAME_SAMPLES)

        if self._is_speech(to_float32(frame)):
            if self._voiced_start_ms is None:
                self._voiced_start_ms = start_ms
            self._voiced.extend(frame)
            self._voiced_end_ms = end_ms
            self._silence_run = 0
            return None

        if self._voiced_start_ms is None:
            return None

        self._silence_run += 1
        if self._silence_run > self._hangover_frames:
            return self._close()
        return None

    def _close(self) -> VoicedSegment | None:
        if self._voiced_start_ms is None or not self._voiced:
            self._reset_segment()
            return None
        segment = VoicedSegment(
            start_ms=self._voiced_start_ms,
            end_ms=self._voiced_end_ms,
            samples=tuple(self._voiced),
        )
        self._reset_segment()
        return segment

    def _reset_segment(self) -> None:
        self._voiced = []
        self._voiced_start_ms = None
        self._voiced_end_ms = 0
        self._silence_run = 0


def silero_is_speech(*, threshold: float = 0.5) -> IsSpeech:
    try:
        import torch
        from silero_vad import load_silero_vad
    except ImportError as exc:
        raise AudioError("silero-vad is not installed") from exc

    model = load_silero_vad(onnx=True)

    def detect(frame: NDArray[np.float32]) -> bool:
        probability = model(torch.from_numpy(np.ascontiguousarray(frame)), BRIDGE_SAMPLE_RATE)
        return bool(float(probability.item()) >= threshold)

    return detect


class TranscriptPipeline:
    """Turns gated audio into one partial stream and one final event per voiced segment."""

    def __init__(
        self,
        provider: STTProvider,
        gate: VadGate,
        *,
        speaker: Speaker = "A",
        language: str | None = None,
    ) -> None:
        self._provider = provider
        self._gate = gate
        self._speaker = speaker
        self._language = language

    def push(self, samples: Sequence[int]) -> list[Transcript]:
        return self._transcribe(self._gate.push(samples))

    def flush(self) -> list[Transcript]:
        return self._transcribe(self._gate.flush())

    def _transcribe(self, segments: Sequence[VoicedSegment]) -> list[Transcript]:
        events: list[Transcript] = []
        for segment in segments:
            segment_id = str(uuid.uuid4())
            for part in self._provider.transcribe(
                to_float32(segment.samples), language=self._language
            ):
                events.append(self._event(part, segment, segment_id))
        return events

    def _event(self, part: SegmentPart, segment: VoicedSegment, segment_id: str) -> Transcript:
        if not part.final:
            return PartialTranscript(
                speaker=self._speaker, text=part.text, segment_id=segment_id
            )
        return FinalTranscript(
            speaker=self._speaker,
            text=part.text,
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            confidence=part.confidence,
            segment_id=segment_id,
        )


def read_wav(path: Path) -> list[int]:
    resolved = Path(path)
    if not resolved.is_file():
        raise AudioError("wav path is not a readable file")
    try:
        with wave.open(str(resolved), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            raw = handle.readframes(handle.getnframes())
    except (wave.Error, EOFError) as exc:
        raise AudioError("wav could not be decoded") from exc
    if channels != BRIDGE_CHANNELS:
        raise AudioError("wav must be single-channel")
    if width != SAMPLE_WIDTH_BYTES:
        raise AudioError("wav must be 16-bit")
    if rate != BRIDGE_SAMPLE_RATE:
        raise AudioError("wav must be 16 kHz")
    return [int(value) for value in np.frombuffer(raw, dtype="<i2")]


def transcribe_wav(path: Path, provider: STTProvider, *, language: str | None = None) -> str:
    samples = read_wav(path)
    if not samples:
        return ""
    spoken = ""
    for part in provider.transcribe(to_float32(samples), language=language):
        spoken = part.text
    return spoken


def default_provider(config: AppConfig | None = None) -> STTProvider:
    settings = config or AppConfig()
    if settings.stt_provider != "faster-whisper":
        raise SttError("configured speech-to-text provider is not available locally")
    from .stt.faster_whisper import FasterWhisperProvider

    return FasterWhisperProvider(
        settings.stt_model_dir or settings.stt_model,
        device=settings.stt_device,
        compute_type=settings.stt_compute_type,
    )


def _err_reply(req_id: str, code: ErrorCode, message: str, retryable: bool = False) -> Reply:
    return Reply(id=req_id, error=ErrorBody(code=code, message=message, retryable=retryable))


async def handle_transcribe_audio(
    request: Request,
    emit: Emit,
    *,
    provider: STTProvider | None = None,
    timeout_s: float = DEFAULT_TRANSCRIBE_TIMEOUT_S,
) -> Reply:
    raw_path = request.params.get("wav_path")
    if not isinstance(raw_path, str) or not raw_path:
        return _err_reply(
            request.id, ErrorCode.INVALID_REQUEST, "`wav_path` must be a non-empty string"
        )
    language = request.params.get("language")
    if language is not None and not isinstance(language, str):
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, "`language` must be a string")

    try:
        active = provider or default_provider()
    except SttError as exc:
        return _err_reply(request.id, ErrorCode.PROVIDER_UNAVAILABLE, str(exc), retryable=True)

    work = functools.partial(transcribe_wav, Path(raw_path), active, language=language)
    loop = asyncio.get_running_loop()
    try:
        text = await asyncio.wait_for(loop.run_in_executor(None, work), timeout=timeout_s)
    except AudioError as exc:
        return _err_reply(request.id, ErrorCode.INVALID_REQUEST, str(exc))
    except SttError as exc:
        return _err_reply(request.id, ErrorCode.PROVIDER_UNAVAILABLE, str(exc), retryable=True)
    except TimeoutError:
        return _err_reply(
            request.id,
            ErrorCode.PYTHON_TIMEOUT,
            "transcription exceeded its budget",
            retryable=True,
        )
    return Reply(id=request.id, result={"text": text})
