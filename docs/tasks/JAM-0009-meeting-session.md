---
id: JAM-0009
title: Meeting session lifecycle and transcript persistence
status: blocked
type: feat
priority: P0
labels: [meetings, transcript, ipc]
milestone: m3-meeting-memory
assigned-to: unassigned
---

## Blocked by

- JAM-0002 — event-capable IPC transport.
- JAM-0007 — meeting and transcript store.
- JAM-0008 — transcript event pipeline.

## Context

JAM-0008 can produce transcript events, but a meeting needs a coherent start, live accumulation, stop, and recovery lifecycle. This task connects audio/STT events to the SQLite store and implements `meeting.start`, `meeting.stop`, `meeting.list`, and `meeting.get`. It depends on JAM-0002, JAM-0007, and JAM-0008.

## Scope: files to touch

- `ai/src/jamly/meetings/__init__.py` (new) — session state machine and persistence orchestration.
- `ai/src/jamly/agent/checkpoint.py` (new) — session recovery checkpoint factory keyed by meeting ID.
- `ai/src/jamly/protocol.py`, `__main__.py` (modify) — meeting method handlers/events.
- `src-tauri/src/bridge.rs`, `lib.rs` (modify if lifecycle wiring is required).
- `tests/unit/test_meetings.py`, `tests/integration/test_meeting_session.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [x] Start creates a durable meeting ID and rejects duplicate active sessions safely.
- [x] Partial/final utterances persist in order and survive process restart.
- [x] Stop flushes pending work, closes the session, and emits `meeting.ended` exactly once.
- [x] List/get return stable, bounded results with search support.
- [x] Cancellation and sidecar EOF leave no orphan active meeting without recovery metadata.

## Definition of Done

- [x] State-machine tests, persistence integration tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for IPC schema changes or database migration conflicts and ping owners.

## Verification

```bash
just verify-jam-0009
```
