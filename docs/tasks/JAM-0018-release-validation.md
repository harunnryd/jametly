---
id: JAM-0018
title: Cross-platform packaging update and north-star validation
status: blocked
type: chore
priority: P0
labels: [release, packaging, e2e, security]
milestone: m6-release-readiness
assigned-to: unassigned
---

## Blocked by

- JAM-0016 — transcript export surface.
- JAM-0017 — production window/stealth lifecycle.
- JAM-0022 — packaged Python sidecar and installer integration.
- Completion of all earlier P0 acceptance criteria.

## Context

The project is complete only when a clean machine can install it, run a meeting workflow, and pass the invisibility and recall tests. This task validates signed/bundled installers, sidecar distribution, updates, permissions, and the end-to-end north-star journey on supported platforms. It depends on every preceding task, especially JAM-0016 and JAM-0017.

## Scope: files to touch

- `src-tauri/tauri.conf.json`, `src-tauri/capabilities/`, bundle assets (modify).
- `.github/workflows/release.yml` and build scripts (modify).
- `tests/e2e/recall.spec.ts`, `tests/e2e/install.spec.ts` (new).
- `SECURITY.md`, `README.md`, `CHANGELOG.md`, and release documentation (modify).
- `justfile` (modify) — add release validation recipe.

## Acceptance Criteria

- [ ] Clean-install smoke passes for macOS, Windows, and Linux target artifacts on the matrix listed in the release workflow.
- [ ] JAM-0022's packaged sidecar is discoverable and starts without `uv` or a development checkout.
- [ ] Update metadata and signatures are validated without runtime telemetry or cloud application calls.
- [ ] Invisibility test passes for the idle app with documented ScreenCaptureKit limitations.
- [ ] Recall test recovers action items and transcript exports from a seeded one-hour meeting fixture.
- [ ] Recall validation checks the default transcript path and its contents after a completed meeting.
- [ ] `just verify-full` passes on the release runner, with any platform-specific skipped test named in this task and the release log.

## Definition of Done

- [ ] Release artifacts, signatures, installation tests, north-star evidence, security review, changelog, recipe, and CI are complete.
- [ ] PR is merged and all task statuses for the completed release milestone are updated.

## Escalation rules

- Stop for signing secrets, HIGH audit findings, release changes, or privacy regressions and ping the relevant owner.

## Verification

```bash
just verify-jam-0018
```
