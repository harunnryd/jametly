---
id: JAM-0028
title: Native monitor and region screen capture
status: blocked
type: feat
priority: P1
labels: [capture, rust, platform]
milestone: m2-capture-and-transcription
assigned-to: unassigned
---

## Blocked by

- JAM-0005 — platform-neutral capture and blob contract.
- `@tooling-owner` approval for xcap and the workspace MSRV strategy.

## Context

JAM-0005 provides deterministic capture validation, PNG storage, and sanitized errors. This task adds real monitor enumeration and screenshot capture using an approved xcap version. Current xcap region APIs require a newer Rust toolchain than the workspace MSRV, so the dependency and MSRV decision must be explicit before implementation.

## Scope: files to touch

- `core/screen-capture/Cargo.toml` (modify) — approved target/platform dependencies.
- `core/screen-capture/src/native.rs` (new) — monitor enumeration and capture adapter.
- `src-tauri/src/capture.rs` (modify) — `capture.screenshot` and `capture.region` commands.
- `.github/workflows/build-smoke.yml`, `release.yml` (modify) — Linux X11/Wayland build packages.
- `tests/integration/test_capture_contract.py` and platform smoke tests (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] Primary-monitor and region capture use real platform displays when available.
- [ ] Region validation remains owned by Jametly and is checked before xcap calls.
- [ ] Permission denial, headless sessions, and unsupported compositors map to sanitized typed errors.
- [ ] Linux CI declares required X11/Wayland/PipeWire build packages and skips unavailable display smoke tests explicitly.
- [ ] macOS behavior matches ADR-0006 and does not claim ScreenCaptureKit invisibility.
- [ ] Captured PNGs are written only through the JAM-0005 blob store.

## Definition of Done

- [ ] Acceptance criteria, dependency/MSRV approval, platform tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new dependencies, MSRV changes, entitlements, capture permissions, or HIGH audit findings and ping the relevant owners.

## Verification

```bash
just verify-jam-0028
```
