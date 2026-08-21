---
id: JAM-XXXX
title: <one-line>
status: ready | in_progress | blocked | closed
type: feat | bug | refactor | chore | test | docs
priority: P0 | P1 | P2 | P3
labels: []
milestone: <e.g. m0-skeleton-bridge>
assigned-to: <gh-handle or "unassigned">
---

## Blocked by

- `none` for a ready task, or list prerequisite tasks and owner approvals for a blocked task.

## Context

3-5 sentences. Why this matters. Link to a design doc or ADR (`../decisions/0001-…md`) if the task pivots on an architectural choice.

## Scope: files to touch

- `path/to/file.py` (new | modify) — one-line purpose
- `path/to/other.rs` (modify) — one-line purpose
- `docs/tasks/JAM-XXXX.md` (modify) — checklist update

## Acceptance Criteria

- [ ] Criterion one — verifiable
- [ ] Criterion two — verifiable
- [ ] Criterion three — verifiable

## Definition of Done

These checks are inherited by every task, even when a task file adds a shorter task-specific checklist.

- [ ] Every Acceptance Criterion above is checked
- [ ] `just verify` exits 0 (PR gate)
- [ ] `just verify-ci` exits 0 once (CI parity)
- [ ] **Tests were written red first, then made green** (TDD Three Rules; see `docs/conventions/TEST_STRATEGY.md`)
- [ ] Coverage thresholds in `docs/conventions/TEST_STRATEGY.md` not regressed
- [ ] `CHANGELOG.md` updated under "Unreleased"
- [ ] PR opened using `.github/PULL_REQUEST_TEMPLATE.md`, CI green
- [ ] PR comments use [Conventional Comments](../conventions/CONVENTIONAL_COMMENTS.md) labels
- [ ] At least one CODEOWNERS reviewer requested
- [ ] Task file's `status: closed` set after PR merges

## Escalation rules

- If missing tool or failing install → STOP, ping `@tooling-owner`
- If need to change IPC schema → STOP, ping `@ipc-owner`
- If need to add a new dependency → STOP, ping `@tooling-owner`, justify in PR body
- If `cargo audit` reports HIGH → STOP, open `sec:` issue, ping `@security-owner`
- If you wrote tests AFTER the implementation → you broke TDD; revert and re-do red-then-green
- If a local pass fails in CI → read the CI log once; if still blocked, ping `@tooling-owner`
- If a test is flaky (<5%) → quarantine it with the project flaky marker and file a follow-up task
- If the task exceeds one day → STOP and split it into child tasks

## Verification

```bash
just verify-<task-id-lowercase>   # e.g. just verify-jam-0042
```

This expands to whatever subset of the project's verify suite applies to the changed files. See `justfile` for the canonical recipe list and `docs/conventions/TEST_STRATEGY.md` for the per-tier gate.
