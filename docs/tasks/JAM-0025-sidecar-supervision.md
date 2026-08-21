---
id: JAM-0025
title: Sidecar crash detection and restart supervision
status: blocked
type: feat
priority: P1
labels: [ipc, resilience, ai]
milestone: m1-full-duplex-ipc
assigned-to: unassigned
---

## Blocked by

- JAM-0002 — event routing and EOF handling.
- JAM-0003 — async sidecar runtime.

## Context

The IPC contract defines `python.crash` and `python.restarted`, but the current task backlog stops at detecting pipe termination. This task owns bounded restart supervision, pending-request failure, and user-visible lifecycle events. It must never create an unbounded restart loop or silently lose meeting data.

## Scope: files to touch

- `src-tauri/src/bridge.rs` and `lib.rs` (modify) — supervisor state machine and lifecycle events.
- `ai/src/jamly/__main__.py` (modify) — clean shutdown and diagnostic metadata.
- `tests/unit/test_supervisor.rs`, `tests/integration/test_sidecar_restart.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] EOF/non-zero exit emits `python.crash` with a bounded diagnostic payload.
- [ ] Restart policy has a finite retry limit and backoff; exhaustion surfaces a terminal error.
- [ ] All pending requests fail deterministically on crash and are not replayed unless explicitly safe.
- [ ] Successful restart emits `python.restarted` with a new process identity.

## Definition of Done

- [ ] Acceptance criteria, resilience tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for process/security policy changes or IPC schema changes and ping owners.

## Verification

```bash
just verify-jam-0025
```
