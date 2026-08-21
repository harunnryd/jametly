---
id: JAM-0006
title: Local configuration and secure provider storage
status: in_progress
type: feat
priority: P0
labels: [config, security, providers]
milestone: m2-capture-and-transcription
assigned-to: unassigned
---

## Blocked by

- None for the dependency-free secure/config contract. Native keychain and TOML persistence are approval-gated in JAM-0029 and JAM-0030.

## Context

Users need local model/provider selection and API keys without cloud-owned configuration or license state. This task creates the config file contract and OS keychain abstraction for provider credentials. It must preserve the privacy boundary: only user-configured provider keys are stored, never telemetry or machine identity.

## Scope: files to touch

- `core/secure-store/` (new) — secret-store trait, approved key namespace, typed errors, and fake store.
- `ai/src/jamly/config.py` (new) — strict non-secret settings defaults and local path contract.
- `src-tauri/src/secure_store.rs` (new) — thin secure-store re-export.
- `shared/schemas/ipc/v1.json` (modify only if the approved config/secure contract requires it) — `config.*` and `secure.get` contracts.
- `tests/unit/test_config.py`, `core/secure-store/tests/` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [x] Config and transcript paths resolve under the documented `~/.config/jametly/` root.
- [x] Secrets are rejected from the config model and never appear in secure-store debug/error output.
- [x] Secure-store operations have typed unavailable/denied errors and a deterministic fake.
- [x] Unknown config keys and invalid values are rejected explicitly.
- [x] Provider keys are restricted to the approved namespace; license/machine identity keys are rejected.
- [x] `cargo test -p secure-store`, focused Python config tests, `just verify`, and `just verify-ci` pass.

## Definition of Done

- [x] Dependency-free contract criteria, coverage, changelog, verification recipe, and CI are complete.
- [x] Native keychain and TOML persistence are tracked separately before dependencies are added.

## Escalation rules

- Stop for keychain plugins, entitlements, or security findings; ping `@security-owner` and `@tooling-owner`.

## Verification

```bash
just verify-jam-0006
```
