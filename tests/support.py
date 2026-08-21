from __future__ import annotations

import math
import os
import socket
import wave
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
from numpy.typing import NDArray

from jamly.audio import BRIDGE_SAMPLE_RATE
from jamly.stt.base import STTProvider, SegmentPart, SttError


class FakeProvider(STTProvider):
    """A deterministic provider that yields real cumulative partials and one final."""

    def __init__(
        self,
        words: tuple[str, ...] = ("hello", "there"),
        *,
        confidence: float = 0.9,
        fail_with: str | None = None,
    ) -> None:
        super().__init__()
        self.words = words
        self.confidence = confidence
        self.fail_with = fail_with
        self.loads = 0
        self.calls = 0
        self.languages: list[str | None] = []

    def _load(self) -> None:
        self.loads += 1

    def transcribe(
        self, pcm: NDArray[np.float32], *, language: str | None = None
    ) -> Iterator[SegmentPart]:
        self.ensure_loaded()
        self.calls += 1
        self.languages.append(language)
        if self.fail_with is not None:
            raise SttError(self.fail_with)
        spoken = ""
        for word in self.words:
            spoken = f"{spoken} {word}".strip()
            yield SegmentPart(text=spoken, final=False, confidence=0.0)
        yield SegmentPart(text=spoken, final=True, confidence=self.confidence)


def speech_like(ms: int, *, seed: int = 0, sample_rate: int = BRIDGE_SAMPLE_RATE) -> list[int]:
    rng = np.random.default_rng(seed)
    count = sample_rate * ms // 1000
    noise = rng.standard_normal(count)
    envelope = 0.5 + 0.5 * np.sin(2 * math.pi * 5.0 * np.arange(count) / sample_rate)
    scaled = np.clip(0.3 * noise * envelope, -1.0, 1.0)
    return [int(value) for value in scaled * 32767]


def silence(ms: int, *, sample_rate: int = BRIDGE_SAMPLE_RATE) -> list[int]:
    return [0] * (sample_rate * ms // 1000)


def write_wav(path: Path, samples: list[int], *, sample_rate: int = BRIDGE_SAMPLE_RATE) -> Path:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(np.asarray(samples, dtype="<i2").tobytes())
    return path


def ollama_reachable(url: str | None = None, *, timeout: float = 2.0) -> bool:
    target = url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    parsed = urlparse(target)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
