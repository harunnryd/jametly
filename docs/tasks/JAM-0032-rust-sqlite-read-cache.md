---
id: JAM-0032
title: Rust SQLite read-cache and typed history queries
status: blocked
type: feat
priority: P1
labels: [database, rust, cache]
milestone: m3-meeting-memory
assigned-to: unassigned
---

## Blocked by

- JAM-0007 — canonical Python-owned SQLite schema.
- JAM-0031 — finalized vector/FTS schema if query parity requires it.
- `@tooling-owner` approval for Rust SQLite dependencies.

## Context

Python remains the owner of database writes, while Rust may maintain a read-only cache for responsive UI queries. This task adds typed Rust read models and bounded history queries without allowing a second writer or divergent migration authority.

## Scope: files to touch

- `core/sqlite-store/` (new) — read-only query models and cache lifecycle.
- `src-tauri/src/db/` (new) — Tauri read commands and refresh/invalidation wiring.
- `tests/unit/` and Rust integration tests (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] Rust opens the canonical database read-only and never performs writes/migrations.
- [ ] Query results match Python repository semantics and have bounded limits.
- [ ] Cache invalidation handles meeting end and database replacement safely.
- [ ] Missing/corrupt database states return typed errors without crashes.

## Definition of Done

- [ ] Acceptance criteria, dependency approval, tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new Rust database dependencies, migration changes, or second-writer behavior and ping owners.

## Verification

```bash
just verify-jam-0032
```
