---
id: JAM-0022
title: Package the Python sidecar with release artifacts
status: blocked
type: feat
priority: P0
labels: [release, packaging, sidecar, tauri]
milestone: m6-release-readiness
assigned-to: unassigned
---

## Blocked by

- JAM-0003 — async sidecar runtime contract.
- JAM-0016 — export surface included in release artifacts.
- JAM-0017 — production window and permission lifecycle.
- `@tooling-owner` and `@release-owner` approval for packaging/signing.

## Context

The development bridge currently starts the sidecar through `uv run --project ai`, which requires a repository checkout and cannot work in a packaged application. This task creates the production sidecar artifact, wires it into Tauri external binaries, and validates platform-specific discovery and permissions. It must preserve the same stdio contract used in development.

## Scope: files to touch

- `ai/pyoxidizer.bzl` or the approved sidecar packaging configuration (new).
- `src-tauri/binaries/` and `tauri.conf.json` (modify) — target-specific sidecar artifacts.
- `src-tauri/src/bridge.rs` (modify) — development vs packaged command selection.
- `.github/workflows/release.yml` (modify) — build, sign, checksum, and upload artifacts.
- `tests/e2e/packaged_sidecar.spec.ts` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] A clean packaged app starts the sidecar without `uv`, a repository checkout, or source-path assumptions.
- [ ] Development mode continues to use the documented uv command.
- [ ] Sidecar target triples and executable permissions are validated on macOS, Windows, and Linux.
- [ ] Release artifacts include signatures/checksums without committing secrets.
- [ ] Packaged smoke tests complete an echo/event round-trip through the production binary.

## Definition of Done

- [ ] Acceptance criteria, release/security review, tests, artifact validation, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for signing secrets, new packaging dependencies, release workflow changes, or security findings and ping the relevant owners.

## Verification

```bash
just verify-jam-0022
```
