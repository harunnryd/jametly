---
id: JAM-0025
title: Sidecar crash detection and restart supervision
status: in_progress
type: feat
priority: P1
labels: [ipc, resilience, ai]
milestone: m1-full-duplex-ipc
assigned-to: harunnryd
---

## Blocked by

- ~~JAM-0002 — event routing and EOF handling.~~ merged.
- ~~JAM-0003 — async sidecar runtime.~~ merged.

## Context

The IPC contract defines `python.crash` and `python.restarted`, but the current task backlog stops at detecting pipe termination. This task owns bounded restart supervision, pending-request failure, and user-visible lifecycle events. It must never create an unbounded restart loop or silently lose meeting data.

## Scope: files to touch

- `src-tauri/src/bridge.rs` and `lib.rs` (modify) — supervisor state machine and lifecycle events.
- `ai/src/jamly/__main__.py` (modify) — clean shutdown and diagnostic metadata.
- `src-tauri/src/supervisor.rs` (new) — restart policy, exit classification, lifecycle events.
- Rust supervisor tests live inline in `src-tauri/src/supervisor.rs`; `tests/` at the repo root is a Python package, so a `.rs` file there would never be compiled by cargo.
- `tests/unit/test_sidecar_shutdown.py`, `tests/integration/test_sidecar_restart.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [x] EOF/non-zero exit emits `python.crash` with a bounded diagnostic payload.
- [x] Restart policy has a finite retry limit and backoff; exhaustion surfaces a terminal error.
- [x] All pending requests fail deterministically on crash and are not replayed unless explicitly safe.
- [x] Successful restart emits `python.restarted` with a new process identity.

## Definition of Done

- [x] Acceptance criteria, resilience tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for process/security policy changes or IPC schema changes and ping owners.

## Verification

```bash
just verify-jam-0025
```
