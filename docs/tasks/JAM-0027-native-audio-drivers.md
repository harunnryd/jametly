---
id: JAM-0027
title: Native microphone and loopback audio drivers
status: blocked
type: feat
priority: P0
labels: [audio, rust, platform]
milestone: m2-capture-and-transcription
assigned-to: unassigned
---

## Blocked by

- JAM-0004 — platform-neutral audio backend contract.
- `@tooling-owner` approval for `cpal`, `cidre`, `wasapi`, and PulseAudio dependencies.

## Context

JAM-0004 establishes the dependency-free audio contract and deterministic mock. This task adds real microphone and system-loopback implementations behind that contract using target-gated native dependencies. It must keep device-dependent tests out of normal CI while preserving the 16 kHz mono bridge boundary.

## Scope: files to touch

- `core/audio-backend/Cargo.toml` (modify) — target-gated native dependencies.
- `core/audio-backend/src/{macos,windows,linux}.rs` (new) — native capture implementations.
- `core/audio-backend/src/lib.rs` (modify) — target-specific backend factory.
- `.github/workflows/build-smoke.yml`, `release.yml` (modify) — Linux audio system packages.
- `tests/perf/` and platform smoke tests (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] Microphone capture works through `cpal` on supported platforms.
- [ ] Loopback capture uses `cidre` on macOS, `wasapi` on Windows, and PulseAudio monitor sources on Linux.
- [ ] Native formats are converted to 16 kHz mono PCM before entering `FrameStream`.
- [ ] Device loss maps to `CaptureError::DeviceLost` without crashing the host.
- [ ] Dependencies are target-gated so `--all-features` never compiles another OS's backend.
- [ ] Mock-based tests remain deterministic; real-device tests are explicit platform smoke tests.

## Definition of Done

- [ ] Acceptance criteria, owner approval, platform tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new dependencies, entitlements, platform APIs, or HIGH audit findings and ping the relevant owners.

## Verification

```bash
just verify-jam-0027
```
