---
id: JAM-0011
title: Ask graph with meeting context and citations
status: blocked
type: feat
priority: P0
labels: [agent, llm, meetings, chat]
milestone: m4-assistant
assigned-to: unassigned
---

## Blocked by

- JAM-0007 — local history store.
- JAM-0005 — screenshot capture and blob paths.
- JAM-0008 — STT pipeline and transcript events.
- JAM-0009 — meeting session context.
- JAM-0010 — streaming LLM provider boundary.

## Context

The provider stream is useful only when it can answer questions against the active meeting and saved history. This task adds the LangGraph Ask flow, bounded context assembly, screenshot/STT/history read-only tools, and source citations without side effects. It depends on JAM-0005, JAM-0007, JAM-0008, JAM-0009, and JAM-0010.

## Scope: files to touch

- `ai/src/jamly/agent/__init__.py` (modify) — Ask graph and state model.
- `ai/src/jamly/agent/tools.py` (new) — read-only screenshot/history/STT tools used by the graph.
- `ai/src/jamly/agent/checkpoint.py` (new) — per-meeting checkpoint factory.
- `tests/unit/test_ask_graph.py`, `tests/integration/test_ask_stream.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] Ask answers use a bounded rolling transcript context and identify source utterance IDs.
- [ ] Graph checkpoints are isolated by meeting/thread ID and recover after restart.
- [ ] Tool calls are observable as events and read-only tools cannot mutate meeting state.
- [ ] Cancellation, empty context, provider error, and prompt overflow are handled deterministically.
- [ ] Recorded/fake model tests validate behavior without mocking the graph into a tautology.

## Definition of Done

- [ ] Graph tests, checkpoint tests, evaluation fixtures, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new tool side effects, network calls, or schema changes and ping owners.

## Verification

```bash
just verify-jam-0011
```
