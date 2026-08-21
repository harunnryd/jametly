---
id: JAM-0008
title: Local speech-to-text pipeline with partial and final events
status: in_progress
type: feat
priority: P0
labels: [stt, audio, ai]
milestone: m3-meeting-memory
assigned-to: unassigned
---

## Blocked by

- ~~JAM-0004 — cross-platform audio backend.~~ Merged as `f662fe5`.
- ~~JAM-0006 — local model/provider configuration.~~ Merged as `5de0a8a`.
- ~~JAM-0003 — async runtime and cancellation.~~ Merged as `d3eed6e`.

## Context

The audio backend produces PCM frames, but users need transcript events with bounded latency. This task adds the STT provider abstraction and local faster-whisper implementation behind the existing event bus. Persistence is owned by JAM-0009; provider fallback behavior remains explicit and local-first.

## Scope: files to touch

- `ai/src/jamly/stt/base.py` (new) — provider protocol and partial/final event semantics.
- `ai/src/jamly/stt/faster_whisper.py` (new) — local CTranslate2 Whisper adapter.
- `ai/src/jamly/audio.py` (new) — PCM ingest, chunking, silero-VAD gating, and provider orchestration.
- `ai/src/jamly/__main__.py` (modify) — `transcribe.audio` request handler for one-shot WAV transcription.
- `tests/unit/test_stt.py`, `tests/property/test_audio_chunker.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [x] PCM chunks preserve ordering and no chunk exceeds the configured duration. Pinned by `tests/property/test_audio_chunker.py::test_chunking_preserves_every_sample_in_order` and `test_no_chunk_exceeds_the_budget`.
- [x] VAD emits voiced segments and suppresses silence using a named 30 ms frame budget. The 30 ms / 480-sample ingest cadence is drained into the exact 512-sample (32 ms) frames silero requires by a ring buffer in `VadGate`. Pinned by `tests/unit/test_stt.py::test_vad_gate_drains_exactly_512_sample_frames_from_a_30ms_cadence` and the property tests `test_audio_chunker.py::test_the_vad_gate_only_ever_sees_full_frames`.
- [x] Partial events carry `speaker: "A"|"B"`, `text`, and `segment_id`; final events carry `speaker: "A"|"B"`, `text`, `start_ms`, `end_ms`, and `confidence`. Pinned by `tests/unit/test_stt.py::test_partial_events_carry_speaker_text_and_segment_id`, `test_final_events_carry_speaker_text_bounds_and_confidence`, and the pydantic `extra="forbid"` envelope.
- [x] Provider/model loading is lazy and errors are typed without leaking audio. `STTProvider.ensure_loaded()` defers the model load; `SttError` carries a short status string; `ProviderFromImportError` is the typed path for the missing-`faster-whisper` case. Pinned by `test_provider_defers_loading_until_the_first_transcription` and `test_faster_whisper_provider_defers_its_import`.
- [x] Empty audio, cancellation, model failure, and slow inference are bounded and tested. `transcribe_wav` returns `""` on empty input; `handle_transcribe_audio` runs inference in `run_in_executor` so cancellation propagates, and `TimeoutError` maps to `PYTHON_TIMEOUT` with `retryable=True`. Pinned by `test_transcribe_audio_handler_is_cancellable`, `test_transcribe_audio_handler_bounds_slow_inference`, and `test_transcribe_audio_handler_maps_provider_failure_to_provider_unavailable`.
- [x] Local faster-whisper is the default path; any remote provider is opt-in and documented. `AppConfig.stt_provider` defaults to `"faster-whisper"`; `default_provider` rejects any other value with a typed `SttError`. Remote providers are explicitly out of scope and owned by JAM-0020.
- [x] `transcribe.audio` accepts a validated local WAV path and returns `{text}` with the same error mapping as live transcription. Pinned by `test_transcribe_audio_handler_returns_text`, `test_transcribe_audio_handler_rejects_a_missing_wav_path`, `test_transcribe_wav_rejects_a_wrong_sample_rate`, and the rest of `test_transcribe_wav_*`.
- [x] Performance budgets and coverage gates pass without requiring model downloads in normal CI. `tests/perf/test_audio_budget.py` enforces the frame budget; `tests/conftest.py` sets `HF_HUB_OFFLINE=1` for the session; all model-touching tests run against a deterministic `FakeProvider`. `just verify` is green (17 s).

## Definition of Done

- [x] Acceptance criteria, model fixture strategy, performance test, changelog, recipe, and CI are complete. **Scope touchpoints outside the declared list:** `ai/src/jamly/bridge.py` (live handler registry; the dead sync `__main__` registry would have been a no-op) and `ai/src/jamly/db.py` (schema v2 adds `segment_id` so JAM-0009 has a persistent home for it).

## Escalation rules

- Stop for new model/runtime dependencies or any runtime cloud call; ping `@tooling-owner` and security owners.

## Verification

```bash
just verify-jam-0008
```
