"""Local CTranslate2 Whisper provider whose import and model load both stay lazy.

Not the place for remote speech-to-text: this adapter never opens a socket, and
`local_files_only` keeps a missing model a typed error rather than a download.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .base import STTProvider, SegmentPart, SttError

DEFAULT_DEVICE = "cpu"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_CPU_THREADS = 4
NO_SPEECH_CEILING = 0.6
COMPRESSION_RATIO_CEILING = 2.4


def seconds_to_ms(seconds: float) -> int:
    if not math.isfinite(seconds) or seconds <= 0:
        return 0
    return int(seconds * 1000)


def normalise_confidence(avg_logprob: float) -> float:
    if not math.isfinite(avg_logprob):
        return 0.0
    return float(min(1.0, max(0.0, math.exp(min(0.0, avg_logprob)))))


class FasterWhisperProvider(STTProvider):
    def __init__(
        self,
        model: str | Path,
        *,
        device: str = DEFAULT_DEVICE,
        compute_type: str = DEFAULT_COMPUTE_TYPE,
        cpu_threads: int = DEFAULT_CPU_THREADS,
        local_files_only: bool = True,
    ) -> None:
        super().__init__()
        self.model = str(model)
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self.local_files_only = local_files_only
        self._whisper: Any | None = None

    def _load(self) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise SttError("faster-whisper is not installed") from exc
        try:
            self._whisper = WhisperModel(
                self.model,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
                local_files_only=self.local_files_only,
            )
        except Exception as exc:
            raise SttError("whisper model could not be loaded") from exc

    def transcribe(
        self, pcm: NDArray[np.float32], *, language: str | None = None
    ) -> Iterator[SegmentPart]:
        self.ensure_loaded()
        whisper = self._whisper
        if whisper is None:
            raise SttError("whisper model is unavailable")
        try:
            segments, _info = whisper.transcribe(
                pcm,
                language=language,
                vad_filter=False,
                condition_on_previous_text=False,
            )
        except Exception as exc:
            raise SttError("transcription failed") from exc

        spoken = ""
        confidence = 0.0
        try:
            for segment in segments:
                if segment.no_speech_prob > NO_SPEECH_CEILING:
                    continue
                if segment.compression_ratio > COMPRESSION_RATIO_CEILING:
                    continue
                spoken = f"{spoken} {segment.text.strip()}".strip()
                confidence = normalise_confidence(segment.avg_logprob)
                yield SegmentPart(text=spoken, final=False, confidence=0.0)
        except SttError:
            raise
        except Exception as exc:
            raise SttError("transcription failed") from exc
        finally:
            close = getattr(segments, "close", None)
            if close is not None:
                close()
        yield SegmentPart(text=spoken, final=True, confidence=confidence)
