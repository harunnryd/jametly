---
id: JAM-0031
title: Local vector search and hybrid meeting index
status: blocked
type: feat
priority: P1
labels: [database, search, embeddings, ai]
milestone: m3-meeting-memory
assigned-to: unassigned
---

## Blocked by

- JAM-0007 — Python SQLite/FTS5 store.
- `@tooling-owner` approval for sqlite-vec and local embedding dependencies.

## Context

JAM-0007 provides deterministic lexical FTS5 search without external dependencies. This task adds local embeddings and sqlite-vec/vec0 hybrid ranking for history retrieval while preserving a lexical fallback when vector extensions or models are unavailable. No remote embedding provider is permitted by default.

## Scope: files to touch

- `ai/src/jamly/meetings/index.py` (new) — embedding generation and hybrid search.
- `ai/src/jamly/db.py` and migrations (modify) — vector table/versioning.
- `ai/pyproject.toml`, `uv.lock` (modify) — approved local embedding dependencies.
- `tests/unit/test_vector_index.py`, integration/property tests (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] Local embeddings are deterministic for fixtures and never require runtime cloud calls.
- [ ] FTS5 and vector results combine with deterministic ranking and bounded result counts.
- [ ] Missing extension/model falls back to FTS5 without corrupting the database.
- [ ] Append/update/delete keeps lexical and vector indexes consistent.

## Definition of Done

- [ ] Acceptance criteria, dependency approval, tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new dependencies, model downloads, extension loading, or network behavior and ping owners.

## Verification

```bash
just verify-jam-0031
```
