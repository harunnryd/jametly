---
id: JAM-0021
title: History append prompts and clipboard tools
status: blocked
type: feat
priority: P1
labels: [agent, history, prompts, tools]
milestone: m5-vision-and-history
assigned-to: unassigned
---

## Blocked by

- JAM-0007 — local history/search store.
- JAM-0011 — agent tool boundary.
- JAM-0014 — frontend invocation surface.

## Context

The IPC method list includes history append/list/search, prompt library operations, and a clipboard tool, but the current backlog only covers search display and read-only Ask tools. This task owns those missing user-facing method surfaces with explicit local persistence and side-effect safety. Clipboard access remains user-invoked and observable.

## Scope: files to touch

- `ai/src/jamly/agent/tools.py` (modify) — clipboard and history tools.
- `ai/src/jamly/prompts.py` (new) — prompt list/save/delete store.
- `ai/src/jamly/__main__.py`, protocol, database (modify).
- `app/src/lib/bridge.ts` and `app/src/pages/prompts.tsx` (modify) — typed methods and prompt UI.
- `tests/unit/test_prompts.py`, `tests/integration/test_history_methods.py`, `tests/e2e/prompts.spec.ts` (new).

## Acceptance Criteria

- [ ] History append/list/search uses bounded local results and preserves conversation IDs.
- [ ] Prompt list/save/delete validates content and persists through the configured local store.
- [ ] Clipboard reads require explicit user action and are never sent to remote providers implicitly.
- [ ] Missing, malformed, and unauthorized clipboard states have safe typed errors.
- [ ] UI and integration tests cover the complete local workflow.

## Definition of Done

- [ ] Acceptance criteria, privacy review, tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new permissions, IPC schema changes, or privacy-sensitive behavior and notify owners.

## Verification

```bash
just verify-jam-0021
```
