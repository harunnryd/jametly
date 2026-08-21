from __future__ import annotations

import pytest

from jamly.audio import (
    INGEST_FRAME_SAMPLES,
    VAD_FRAME_SAMPLES,
    TranscriptPipeline,
    VadGate,
    chunk_samples,
    silero_is_speech,
)
from jamly.stt.base import FinalTranscript
from tests.support import FakeProvider, silence, speech_like


def test_real_silero_accepts_every_frame_the_gate_drains() -> None:
    widths: list[int] = []
    detect = silero_is_speech()

    def probe(frame: object) -> bool:
        import numpy as np

        widths.append(len(np.asarray(frame)))
        return detect(frame)  # type: ignore[arg-type]

    gate = VadGate(probe)
    for chunk in chunk_samples(speech_like(900), 30):
        gate.push(list(chunk))
    gate.flush()

    assert widths
    assert set(widths) == {VAD_FRAME_SAMPLES}


def test_real_silero_finds_no_speech_in_any_synthetic_input() -> None:
    gate = VadGate(silero_is_speech())
    segments = []
    for chunk in chunk_samples(speech_like(900) + silence(600), 30):
        segments += gate.push(list(chunk))
    segments += gate.flush()

    assert segments == []


def test_real_silero_processes_every_drained_frame_without_error() -> None:
    frames_seen: list[int] = []

    def probe(frame: object) -> bool:
        import numpy as np

        frames_seen.append(len(np.asarray(frame)))
        return silero_is_speech()(frame)  # type: ignore[arg-type]

    gate = VadGate(probe)
    for chunk in chunk_samples(speech_like(3000), 30):
        gate.push(list(chunk))
    gate.flush()

    assert frames_seen
    assert all(width == VAD_FRAME_SAMPLES for width in frames_seen)


def test_pipeline_drains_the_real_silero_frame_safely() -> None:
    provider = FakeProvider(words=("satu", "dua", "tiga"))
    pipeline = TranscriptPipeline(provider, VadGate(silero_is_speech(), hangover_frames=2))
    for chunk in chunk_samples(speech_like(900) + silence(600), 30):
        pipeline.push(list(chunk))
    pipeline.flush()

    assert pipeline._gate.pending_samples < INGEST_FRAME_SAMPLES  # noqa: SLF001


def test_ingest_cadence_matches_the_documented_frame_budget() -> None:
    assert INGEST_FRAME_SAMPLES == 480
    assert VAD_FRAME_SAMPLES == 512


def test_silero_rejects_the_30ms_frame_the_gate_never_sends() -> None:
    import numpy as np

    detect = silero_is_speech()
    with pytest.raises(Exception):
        detect(np.zeros(INGEST_FRAME_SAMPLES, dtype=np.float32))
