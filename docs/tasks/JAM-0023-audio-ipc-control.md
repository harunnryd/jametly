---
id: JAM-0023
title: Audio control methods and level events
status: blocked
type: feat
priority: P1
labels: [audio, ipc, events]
milestone: m3-meeting-memory
assigned-to: unassigned
---

## Blocked by

- JAM-0002 — event-capable IPC transport.
- JAM-0004 — audio backend abstraction.
- JAM-0027 — native microphone and loopback drivers.
- JAM-0006 — device/configuration selection.

## Context

The architecture defines `audio.start`, `audio.stop`, `audio.frame`, and `audio.level`, but no task currently owns the IPC handlers that connect the Rust capture backend to Python processing and UI diagnostics. This task owns those control methods and explicitly bounded diagnostic events. It does not implement STT or real audio device drivers.

## Scope: files to touch

- `shared/schemas/ipc/v1.json` (modify) — approved audio control params/results.
- `core/ipc-proto/`, `src-tauri/src/audio/`, and `src-tauri/src/bridge.rs` (modify) — typed control/event routing.
- `ai/src/jamly/audio.py`, `__main__.py` (modify) — start/stop handlers and diagnostic level events.
- `tests/unit/test_audio_ipc.py`, `tests/integration/test_audio_control.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] `audio.start` validates `mic`/`loopback` and returns a stable session result.
- [ ] `audio.stop` is idempotent and flushes/terminates the selected stream.
- [ ] `audio.level` is bounded to the documented 10 Hz diagnostic rate.
- [ ] `audio.frame` is diagnostic-only and large payloads use blob paths.
- [ ] Device loss maps to `AUDIO_DEVICE_LOST` and does not crash the sidecar.

## Definition of Done

- [ ] Acceptance criteria, schema approval, tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for IPC schema changes, native device APIs, or new dependencies and ping the relevant owners.

## Verification

```bash
just verify-jam-0023
```
