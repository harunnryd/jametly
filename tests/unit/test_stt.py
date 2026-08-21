from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from tests.support import FakeProvider, silence, speech_like, write_wav

from jamly.audio import (
    BRIDGE_SAMPLE_RATE,
    INGEST_FRAME_SAMPLES,
    VAD_FRAME_SAMPLES,
    AudioError,
    TranscriptPipeline,
    VadGate,
    handle_transcribe_audio,
    transcribe_wav,
)
from jamly.protocol import ErrorCode, Event, Request
from jamly.stt.base import FinalTranscript, PartialTranscript, SttError


def always_speech(frame: object) -> bool:
    return True


def never_speech(frame: object) -> bool:
    return False


def loud_frames(frame: object) -> bool:
    import numpy as np

    return bool(np.abs(np.asarray(frame)).max() > 0.01)


def test_provider_defers_loading_until_the_first_transcription() -> None:
    provider = FakeProvider()
    assert provider.loads == 0


def test_repeated_transcription_loads_the_model_once() -> None:
    import numpy as np

    provider = FakeProvider()
    pcm = np.zeros(1600, dtype=np.float32)
    list(provider.transcribe(pcm))
    list(provider.transcribe(pcm))
    assert provider.loads == 1
    assert provider.calls == 2


def test_vad_gate_drains_exactly_512_sample_frames_from_a_30ms_cadence() -> None:
    seen: list[int] = []

    def record(frame: object) -> bool:
        import numpy as np

        seen.append(len(np.asarray(frame)))
        return True

    gate = VadGate(record)
    for _ in range(15):
        gate.push(speech_like(30))
    assert seen == [VAD_FRAME_SAMPLES] * 14
    assert gate.pending_samples == 15 * INGEST_FRAME_SAMPLES - 14 * VAD_FRAME_SAMPLES


def test_vad_gate_preserves_sample_order_across_frame_boundaries() -> None:
    drained: list[int] = []

    def record(frame: object) -> bool:
        import numpy as np

        drained.extend(int(round(value * 32768)) for value in np.asarray(frame))
        return True

    gate = VadGate(record)
    source = list(range(0, 4096))
    gate.push(source)
    assert drained == source[: len(drained)]


def test_vad_gate_suppresses_silence() -> None:
    gate = VadGate(never_speech)
    gate.push(silence(500))
    assert gate.flush() == []


def test_vad_gate_emits_voiced_segments_with_millisecond_bounds() -> None:
    gate = VadGate(loud_frames, hangover_frames=1)
    segments = []
    segments += gate.push(silence(96))
    segments += gate.push(speech_like(320))
    segments += gate.push(silence(192))
    segments += gate.flush()
    assert segments
    first = segments[0]
    assert first.start_ms >= 0
    assert first.end_ms > first.start_ms


def test_empty_audio_produces_no_frames_and_no_segments() -> None:
    gate = VadGate(always_speech)
    assert gate.push([]) == []
    assert gate.flush() == []
    assert gate.pending_samples == 0


def test_partial_events_carry_speaker_text_and_segment_id() -> None:
    provider = FakeProvider(words=("one", "two"))
    pipeline = TranscriptPipeline(provider, VadGate(always_speech))
    events = pipeline.push(speech_like(120)) + pipeline.flush()
    partials = [event for event in events if isinstance(event, PartialTranscript)]
    assert partials
    for partial in partials:
        assert partial.speaker in ("A", "B")
        assert partial.text
        assert partial.segment_id


def test_final_events_carry_speaker_text_bounds_and_confidence() -> None:
    provider = FakeProvider(words=("one", "two"), confidence=0.75)
    pipeline = TranscriptPipeline(provider, VadGate(always_speech))
    events = pipeline.push(speech_like(120)) + pipeline.flush()
    finals = [event for event in events if isinstance(event, FinalTranscript)]
    assert len(finals) == 1
    final = finals[0]
    assert final.speaker in ("A", "B")
    assert final.text == "one two"
    assert final.end_ms >= final.start_ms
    assert final.confidence == pytest.approx(0.75)


def test_partials_and_the_final_share_one_segment_id() -> None:
    provider = FakeProvider(words=("one", "two"))
    pipeline = TranscriptPipeline(provider, VadGate(always_speech))
    events = pipeline.push(speech_like(120)) + pipeline.flush()
    identifiers = {event.segment_id for event in events}
    assert len(identifiers) == 1


def test_final_confidence_is_confined_to_the_unit_interval() -> None:
    with pytest.raises(ValueError):
        FinalTranscript(speaker="A", text="x", start_ms=0, end_ms=1, confidence=1.5, segment_id="s")
    with pytest.raises(ValueError):
        FinalTranscript(speaker="A", text="x", start_ms=0, end_ms=1, confidence=-0.1, segment_id="s")


def test_final_bounds_reject_a_reversed_span() -> None:
    with pytest.raises(ValueError):
        FinalTranscript(speaker="A", text="x", start_ms=10, end_ms=9, confidence=0.5, segment_id="s")


def test_speaker_is_restricted_to_the_known_union() -> None:
    with pytest.raises(ValueError):
        PartialTranscript(speaker="C", text="x", segment_id="s")


def test_transcript_events_reject_unknown_fields() -> None:
    with pytest.raises(ValueError):
        PartialTranscript(speaker="A", text="x", segment_id="s", extra="nope")


def test_provider_failure_surfaces_a_typed_error_without_audio() -> None:
    provider = FakeProvider(fail_with="model unavailable")
    pipeline = TranscriptPipeline(provider, VadGate(always_speech))
    with pytest.raises(SttError) as caught:
        pipeline.push(speech_like(120))
        pipeline.flush()
    assert "model unavailable" in str(caught.value)
    assert "samples" not in str(caught.value)


def test_transcribe_wav_returns_the_transcribed_text(tmp_path: Path) -> None:
    path = write_wav(tmp_path / "clip.wav", speech_like(400))
    provider = FakeProvider(words=("hello", "world"))
    assert transcribe_wav(path, provider) == "hello world"


def test_transcribe_wav_forwards_the_requested_language(tmp_path: Path) -> None:
    path = write_wav(tmp_path / "clip.wav", speech_like(400))
    provider = FakeProvider()
    transcribe_wav(path, provider, language="id")
    assert provider.languages == ["id"]


def test_transcribe_wav_rejects_a_missing_path(tmp_path: Path) -> None:
    with pytest.raises(AudioError):
        transcribe_wav(tmp_path / "absent.wav", FakeProvider())


def test_transcribe_wav_rejects_a_directory(tmp_path: Path) -> None:
    with pytest.raises(AudioError):
        transcribe_wav(tmp_path, FakeProvider())


def test_transcribe_wav_rejects_a_file_that_is_not_a_wav(tmp_path: Path) -> None:
    path = tmp_path / "clip.wav"
    path.write_bytes(b"not a riff header at all")
    with pytest.raises(AudioError):
        transcribe_wav(path, FakeProvider())


def test_transcribe_wav_rejects_a_wrong_sample_rate(tmp_path: Path) -> None:
    path = write_wav(tmp_path / "clip.wav", speech_like(200, sample_rate=8000), sample_rate=8000)
    with pytest.raises(AudioError):
        transcribe_wav(path, FakeProvider())


def test_transcribe_wav_accepts_empty_audio_as_empty_text(tmp_path: Path) -> None:
    path = write_wav(tmp_path / "clip.wav", [])
    assert transcribe_wav(path, FakeProvider()) == ""


async def test_transcribe_audio_handler_returns_text(tmp_path: Path) -> None:
    path = write_wav(tmp_path / "clip.wav", speech_like(400))
    request = Request(id="1", method="transcribe.audio", params={"wav_path": str(path)})
    reply = await handle_transcribe_audio(request, _discard, provider=FakeProvider(words=("ok",)))
    assert reply.error is None
    assert reply.result == {"text": "ok"}


async def test_transcribe_audio_handler_rejects_a_missing_wav_path() -> None:
    request = Request(id="1", method="transcribe.audio", params={})
    reply = await handle_transcribe_audio(request, _discard, provider=FakeProvider())
    assert reply.error is not None
    assert reply.error.code == ErrorCode.INVALID_REQUEST


async def test_transcribe_audio_handler_maps_a_bad_path_to_invalid_request(tmp_path: Path) -> None:
    request = Request(
        id="1", method="transcribe.audio", params={"wav_path": str(tmp_path / "absent.wav")}
    )
    reply = await handle_transcribe_audio(request, _discard, provider=FakeProvider())
    assert reply.error is not None
    assert reply.error.code == ErrorCode.INVALID_REQUEST
    assert reply.error.retryable is False


async def test_transcribe_audio_handler_maps_provider_failure_to_provider_unavailable(
    tmp_path: Path,
) -> None:
    path = write_wav(tmp_path / "clip.wav", speech_like(200))
    request = Request(id="1", method="transcribe.audio", params={"wav_path": str(path)})
    provider = FakeProvider(fail_with="weights missing")
    reply = await handle_transcribe_audio(request, _discard, provider=provider)
    assert reply.error is not None
    assert reply.error.code == ErrorCode.PROVIDER_UNAVAILABLE
    assert reply.error.retryable is True


async def test_transcribe_audio_handler_never_leaks_the_wav_path_on_failure(tmp_path: Path) -> None:
    path = write_wav(tmp_path / "secret-meeting.wav", speech_like(200))
    request = Request(id="1", method="transcribe.audio", params={"wav_path": str(path)})
    provider = FakeProvider(fail_with="weights missing")
    reply = await handle_transcribe_audio(request, _discard, provider=provider)
    assert reply.error is not None
    assert "secret-meeting" not in reply.error.message


async def test_transcribe_audio_handler_is_cancellable(tmp_path: Path) -> None:
    import threading
    import time

    path = write_wav(tmp_path / "clip.wav", speech_like(400))
    request = Request(id="1", method="transcribe.audio", params={"wav_path": str(path)})
    started = threading.Event()

    class Blocking(FakeProvider):
        def _load(self) -> None:
            started.set()
            time.sleep(0.5)

    task = asyncio.create_task(handle_transcribe_audio(request, _discard, provider=Blocking()))
    while not started.is_set():
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_transcribe_audio_handler_bounds_slow_inference(tmp_path: Path) -> None:
    import time

    path = write_wav(tmp_path / "clip.wav", speech_like(200))
    request = Request(id="1", method="transcribe.audio", params={"wav_path": str(path)})

    class Slow(FakeProvider):
        def _load(self) -> None:
            time.sleep(0.3)

    reply = await handle_transcribe_audio(request, _discard, provider=Slow(), timeout_s=0.02)
    assert reply.error is not None
    assert reply.error.code == ErrorCode.PYTHON_TIMEOUT
    assert reply.error.retryable is True


def test_faster_whisper_provider_defers_its_import(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    from jamly.stt.faster_whisper import FasterWhisperProvider

    provider = FasterWhisperProvider("/nonexistent/model/dir")
    real_import = builtins.__import__

    def refuse(name: str, *args: object, **kwargs: object) -> object:
        if name == "faster_whisper":
            raise ImportError("no faster_whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(SttError):
        provider.ensure_loaded()


def test_faster_whisper_provider_normalises_confidence_into_the_unit_interval() -> None:
    from jamly.stt.faster_whisper import normalise_confidence

    assert normalise_confidence(0.0) == pytest.approx(1.0)
    assert 0.0 < normalise_confidence(-1.0) < 1.0
    assert normalise_confidence(-1000.0) >= 0.0
    assert normalise_confidence(float("-inf")) == 0.0


def test_faster_whisper_provider_converts_seconds_to_milliseconds() -> None:
    from jamly.stt.faster_whisper import seconds_to_ms

    assert seconds_to_ms(0.0) == 0
    assert seconds_to_ms(1.2345) == 1234
    assert seconds_to_ms(-1.0) == 0


async def _discard(_event: Event) -> None:
    return None
