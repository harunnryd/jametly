---
id: JAM-0029
title: Native OS credential-store implementations
status: blocked
type: feat
priority: P0
labels: [security, credentials, rust, platform]
milestone: m2-capture-and-transcription
assigned-to: unassigned
---

## Blocked by

- JAM-0006 — secure-store contract and validated config model.
- `@tooling-owner` and `@security-owner` approval for the keyring dependency strategy.

## Context

JAM-0006 defines the approved provider-key namespace, non-disclosing errors, and deterministic fake store without a native dependency. This task wires macOS Keychain, Windows Credential Manager, and Linux Secret Service behind that contract. The current compatible candidate is a pinned keyring 3.x release; newer keyring generations exceed the workspace MSRV.

## Scope: files to touch

- `core/secure-store/Cargo.toml` (modify) — approved target-gated keyring dependencies.
- `core/secure-store/src/native.rs` (new) — OS credential-store adapter.
- `src-tauri/src/secure_store.rs` (modify) — platform store construction and blocking isolation.
- `.github/workflows/build-smoke.yml`, `release.yml` (modify) — Linux D-Bus build/runtime setup and MSRV check.
- Platform opt-in integration tests, `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] macOS uses Keychain, Windows uses Credential Manager, and Linux uses Secret Service with no plaintext fallback.
- [ ] Missing, denied, unavailable, and backend failures map to the JAM-0006 typed errors without exposing secret values.
- [ ] Dependencies remain compatible with Rust 1.83 or an explicit MSRV change is separately approved.
- [ ] Normal CI uses the deterministic fake; native store tests are explicit opt-in platform jobs.
- [ ] Linux documents and tests the absence of a D-Bus Secret Service session.

## Definition of Done

- [ ] Acceptance criteria, dependency/security approval, native tests, audit, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new dependencies, MSRV changes, secret exposure, permissions, or HIGH audit findings and ping the relevant owners.

## Verification

```bash
just verify-jam-0029
```
