---
id: JAM-0015
title: Meeting history dashboard and transcript search
status: blocked
type: feat
priority: P1
labels: [ui, history, search, meetings]
milestone: m5-vision-and-history
assigned-to: unassigned
---

## Blocked by

- JAM-0007 — searchable local store.
- JAM-0009 — meeting records.
- JAM-0014 — frontend application shell.

## Context

The dashboard is the durable recall surface after the overlay. This task adds meeting history browsing, transcript search, meeting detail, and prompt/history views backed by the local store. It depends on JAM-0007, JAM-0009, and JAM-0014.

## Scope: files to touch

- `app/src/pages/dashboard.tsx`, `meeting.tsx` (new) — history and detail views.
- `app/src/lib/bridge.ts` (modify) — typed history/search methods.
- `src-tauri/src/db/queries.rs` (new, only if the finalized store contract requires it) — Rust read-cache queries.
- `tests/e2e/history.spec.ts`, `app/src/__tests__/history.test.tsx` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] User can list, search, open, and navigate meeting records without cloud calls.
- [ ] Search results identify matching utterances and preserve source timestamps.
- [ ] Empty, large, and unavailable database states render defined empty, paginated, and error states.
- [ ] History views never display stored secrets or raw internal checkpoints.
- [ ] E2E tests cover the recall workflow on a seeded local database.

## Definition of Done

- [ ] Dashboard behavior, seeded E2E, privacy review, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for schema migrations, new frontend dependencies, or privacy regressions.

## Verification

```bash
just verify-jam-0015
```
