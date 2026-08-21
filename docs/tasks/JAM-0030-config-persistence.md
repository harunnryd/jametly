---
id: JAM-0030
title: Atomic TOML config persistence and migrations
status: blocked
type: feat
priority: P1
labels: [config, persistence, ai]
milestone: m2-capture-and-transcription
assigned-to: unassigned
---

## Blocked by

- JAM-0006 — validated non-secret config model and path contract.
- `@tooling-owner` approval for TOML/settings dependencies.

## Context

JAM-0006 defines strict defaults and local paths but does not add file-format dependencies or write user configuration. This task adds atomic `config.toml` load/save, schema versioning, and migrations while preserving the rule that provider secrets never enter the file. It also owns `config.get` and `config.set` method wiring.

## Scope: files to touch

- `ai/src/jamly/config.py` (modify) — TOML load/save and migrations.
- `ai/pyproject.toml`, `uv.lock` (modify) — approved config dependencies.
- `ai/src/jamly/__main__.py`, protocol (modify) — `config.get`/`config.set` handlers.
- `tests/unit/test_config_persistence.py`, integration tests (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] Config writes atomically and a failed write preserves the previous valid file.
- [ ] Unknown keys and invalid values fail with typed errors; older schema versions migrate deterministically.
- [ ] API keys, tokens, and secrets are rejected from serialization and never appear in logs/errors.
- [ ] `config.get` and `config.set` expose only approved non-secret fields.
- [ ] Fresh, missing, malformed, and read-only config paths have deterministic behavior.

## Definition of Done

- [ ] Acceptance criteria, dependency approval, migration tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new dependencies, IPC changes, path/security regressions, or secret serialization and ping owners.

## Verification

```bash
just verify-jam-0030
```
