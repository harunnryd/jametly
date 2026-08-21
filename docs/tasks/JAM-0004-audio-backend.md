---
id: JAM-0004
title: Cross-platform audio backend abstraction
status: in_progress
type: feat
priority: P0
labels: [audio, rust, platform]
milestone: m2-capture-and-transcription
assigned-to: unassigned
---

## Blocked by

- `@tooling-owner` approval for native audio dependencies. **Not required for this task as scoped:** no native audio crate is added, so `Cargo.toml`'s per-OS audio block stays commented out. The approval is still outstanding and gates the per-OS backend follow-ups, not the platform-neutral abstraction.

## Context

jametly needs deterministic PCM frames from microphone and system-loopback sources before transcription can work. This task defines the reusable Rust audio abstraction and bounded frame stream without coupling it to Python or Whisper. The crate can be developed in parallel with the async sidecar and requires platform dependency review before native audio crates are added.

## Scope: files to touch

- `core/audio-backend/Cargo.toml` (new) — standalone Rust crate with dependency-free abstraction and test dependencies.
- `core/audio-backend/src/lib.rs` (new) — backend trait, PCM frame, format, lifecycle, and bounded stream contract.
- `core/audio-backend/src/mock.rs` (new) — deterministic test backend.
- `src-tauri/src/audio/mod.rs` (new) — thin Tauri re-export of the backend contract.
- `core/audio-backend/tests/` (new) — frame, overflow, lifecycle, and property tests.
- `Cargo.toml` (modify) — register the workspace member.
- `docs/architecture/02-modules.md` (modify) — document the real crate.
- `justfile` (modify) — add `verify-jam-0004`.

## Acceptance Criteria

- [x] A platform-neutral trait supports start, stop, format, and frame delivery.
- [x] Frames are 16 kHz mono PCM at the bridge boundary and preserve timestamps.
- [x] The stream is bounded and has an explicit overflow policy.
- [x] Mock capture is deterministic and covers lifecycle/error paths.
- [x] Native dependencies are deferred to approval-gated JAM-0027 and remain target-gated by contract; this task adds no native dependency.
- [x] `cargo test -p audio-backend`, `just verify`, and `just verify-ci` pass.

## Definition of Done

- [x] Platform-neutral acceptance criteria, coverage threshold, changelog, task recipe, and CI are complete.
- [x] Native backend approval remains open and is tracked in JAM-0027 before any per-OS dependency is added.

## Escalation rules

- Stop for new dependencies or platform APIs and ping `@tooling-owner`.
- Stop for public IPC changes and ping `@ipc-owner`.

## Verification

```bash
just verify-jam-0004
```
