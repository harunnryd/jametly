---
id: JAM-0024
title: Q&A graph and guarded tool-interrupt events
status: blocked
type: feat
priority: P1
labels: [agent, qa, events]
milestone: m4-assistant
assigned-to: unassigned
---

## Blocked by

- JAM-0002 — event transport.
- JAM-0010 — provider streaming.
- JAM-0011 — Ask graph state and tools.
- JAM-0021 — history/prompts/clipboard tool surface.

## Context

The architecture lists a Q&A subgraph and `qa.chunk`, `qa.done`, and `qa.interrupt` events, but the current backlog only covers Ask mode. This task owns the Q&A-specific streaming and interrupt contract, including a user-visible guard before any side-effecting tool action. Read-only tools remain non-interrupting.

## Scope: files to touch

- `ai/src/jamly/agent/__init__.py`, `agent/tools.py` (modify) — Q&A graph and interrupt state.
- `ai/src/jamly/protocol.py`, `__main__.py` (modify) — Q&A events and method dispatch.
- `app/src/lib/bridge.ts`, Q&A components (modify).
- `tests/unit/test_qa_graph.py`, `tests/integration/test_qa_events.py`, `tests/e2e/qa.spec.ts` (new).

## Acceptance Criteria

- [ ] Q&A emits ordered `qa.chunk` and exactly one terminal `qa.done` or typed error.
- [ ] Any side-effecting tool emits `qa.interrupt` before execution and waits for explicit user approval.
- [ ] Denied or cancelled actions produce no side effect and a deterministic terminal state.
- [ ] Read-only Ask tools do not emit false interrupt events.

## Definition of Done

- [ ] Acceptance criteria, tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new side effects, permission prompts, schema changes, or provider dependencies and ping owners.

## Verification

```bash
just verify-jam-0024
```
