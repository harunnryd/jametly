---
id: JAM-0007
title: SQLite meeting and transcript store
status: closed
type: feat
priority: P0
labels: [database, meetings, search]
milestone: m3-meeting-memory
assigned-to: unassigned
---

## Blocked by

- None for the Python standard-library SQLite/FTS5 slice. sqlite-vec, embeddings, and the Rust read-cache are approval-gated in JAM-0031 and JAM-0032.

## Context

Meeting transcripts, messages, action items, and checkpoints need durable local storage. Python owns writes while Rust may maintain a read cache, as fixed by the architecture. This task establishes schema migrations, typed repositories, FTS5 search, and the testable persistence boundary before meeting orchestration is added.

## Scope: files to touch

- `ai/src/jamly/db.py` (new) — Python-owned standard-library SQLite write store and migrations.
- `tests/unit/test_db.py`, `tests/integration/test_db_roundtrip.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [x] Database initializes in a fresh app-data directory with deterministic schema version 1 migrations.
- [x] Meeting, utterance, message, and action-item records round-trip with stable IDs.
- [x] Append-then-search works through FTS5 and handles empty/unsafe queries safely with bounded results.
- [x] Transactions roll back on partial failure and foreign-key constraints protect parent records.
- [x] No cloud or telemetry tables are introduced.
- [ ] `history.append`, `history.list`, and `history.search` IPC handlers are wired in a follow-up.
- [ ] sqlite-vec/embedding search and the Rust read-cache are implemented in JAM-0031/JAM-0032.

## Definition of Done

- [x] Python store criteria, coverage, changelog, verification recipe, and CI are complete.
- [x] Vector search and Rust read-cache are explicitly split into follow-up tasks before new dependencies are added.

## Escalation rules

- Stop for schema/API changes affecting IPC or new database extensions and notify owners.

## Verification

```bash
just verify-jam-0007
```
