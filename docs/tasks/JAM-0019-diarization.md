---
id: JAM-0019
title: A/B speaker routing
status: blocked
type: feat
priority: P1
labels: [audio, diarization, transcript, ai]
milestone: m3-meeting-memory
assigned-to: unassigned
---

## Blocked by

- JAM-0004 — audio backend.
- JAM-0008 — VAD and STT segment pipeline.

## Context

Live transcripts need stable speaker labels before summaries and follow-ups can cite who said what. This task owns only the simple A/B routing promised in the current product scope. Advanced live/post-process diarization remains deferred to a future v0.5 task because it is explicitly outside today's goal.

## Scope: files to touch

- `ai/src/jamly/diar/__init__.py` (new) — deterministic A/B routing interface.
- `ai/src/jamly/audio.py` and STT event wiring (modify) — attach speaker labels.
- `tests/unit/test_diarization.py`, `tests/integration/test_speaker_events.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] A/B speaker routing is deterministic for the live path.
- [ ] Advanced live/post-process diarization is explicitly not required by this task and remains unimplemented.
- [ ] Transcript events preserve speaker, segment, and timestamp provenance.
- [ ] Device loss, overlapping speech, and unavailable models have typed fallback behavior.
- [ ] No advanced diarization model is required or loaded by this task or normal CI.

## Definition of Done

- [ ] Acceptance criteria, model approval, tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new model dependencies, privacy changes, or schema changes and notify the relevant owners.

## Verification

```bash
just verify-jam-0019
```
