---
id: JAM-0005
title: Screenshot and region capture pipeline
status: in_progress
type: feat
priority: P1
labels: [capture, rust, platform, ipc]
milestone: m2-capture-and-transcription
assigned-to: unassigned
---

## Blocked by

- None for the pure capture contract. Native xcap integration is approval-gated in JAM-0028.

## Context

The agent and OCR workflows need screenshots without sending raw pixels inline over stdio. This task adds a testable screen-capture core wrapper and tempfile-based request/reply handoff for full-monitor and region captures. It uses the existing bridge and platform permission model without claiming stealth beyond the security disclosure.

## Scope: files to touch

- `core/screen-capture/Cargo.toml` and `src/lib.rs` (new) — capture trait, region validation, PNG blob output, and cleanup.
- `src-tauri/src/capture.rs` (new) — thin Tauri re-export; native commands follow in JAM-0028.
- `shared/schemas/ipc/v1.json` (modify only if the approved capture contract requires it) — capture method params/results.
- `tests/integration/test_capture_contract.py` (new) — path and error contract tests.
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [x] Deterministic full-monitor and validated-region mock capture returns readable PNG paths.
- [x] Invalid, zero-sized, overflowed, and out-of-bounds regions return typed errors.
- [x] Captures use the configured blob directory and return paths, never inline base64.
- [x] Permission denial and unavailable capture are surfaced through sanitized typed errors.
- [x] Blob paths are confined and stale PNG files can be cleaned without deleting unrelated files.
- [x] `cargo test -p screen-capture`, `just verify`, and `just verify-ci` pass.

## Definition of Done

- [x] Pure contract criteria, coverage, changelog, verification recipe, and CI are complete.
- [x] Native capture dependency, permissions, and platform smoke tests are tracked in JAM-0028.

## Escalation rules

- Stop for new capture dependencies, entitlements, or schema changes and notify the relevant owner.

## Verification

```bash
just verify-jam-0005
```
