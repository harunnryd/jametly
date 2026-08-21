from __future__ import annotations

from typing import Any

import numpy as np
from tests.support import speech_like

from jamly.audio import INGEST_FRAME_MS, VAD_FRAME_MS, VadGate, chunk_samples

VAD_FRAME_BUDGET_S = VAD_FRAME_MS / 1000.0


def test_vad_gate_stays_inside_the_frame_budget(benchmark: Any) -> None:
    audible = speech_like(INGEST_FRAME_MS)

    def drive() -> None:
        gate = VadGate(lambda frame: bool(np.abs(np.asarray(frame)).max() > 0.01))
        for _ in range(64):
            gate.push(audible)

    benchmark(drive)
    per_frame = benchmark.stats.stats.median / 64
    assert per_frame < VAD_FRAME_BUDGET_S


def test_chunking_a_second_of_audio_is_cheap(benchmark: Any) -> None:
    source = speech_like(1000)
    benchmark(lambda: chunk_samples(source, INGEST_FRAME_MS))
    assert benchmark.stats.stats.median < 0.05
