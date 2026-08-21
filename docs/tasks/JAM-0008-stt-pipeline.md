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

- [ ] PCM chunks preserve ordering and no chunk exceeds the configured duration.
- [ ] VAD emits voiced segments and suppresses silence using a named 30 ms frame budget.
- [ ] Partial events carry `speaker: "A"|"B"`, `text`, and `segment_id`; final events carry `speaker: "A"|"B"`, `text`, `start_ms`, `end_ms`, and `confidence`.
- [ ] Provider/model loading is lazy and errors are typed without leaking audio.
- [ ] Empty audio, cancellation, model failure, and slow inference are bounded and tested.
- [ ] Local faster-whisper is the default path; any remote provider is opt-in and documented.
- [ ] `transcribe.audio` accepts a validated local WAV path and returns `{text}` with the same error mapping as live transcription.
- [ ] Performance budgets and coverage gates pass without requiring model downloads in normal CI.

## Definition of Done

- [ ] Acceptance criteria, model fixture strategy, performance test, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new model/runtime dependencies or any runtime cloud call; ping `@tooling-owner` and security owners.

## Verification

```bash
just verify-jam-0008
```
