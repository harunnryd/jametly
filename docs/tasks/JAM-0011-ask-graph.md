---
id: JAM-0011
title: Ask graph with meeting context and citations
status: done
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

The provider stream is useful only when it can answer questions against the active meeting and saved history. This task adds the Ask pipeline, bounded rolling transcript context, citation emission, observable read-only tool calls, and per-meeting checkpointing without side effects. It depends on JAM-0005, JAM-0007, JAM-0008, JAM-0009, and JAM-0010.

## Scope: files touched

- `ai/src/jamly/agent/__init__.py` (modify) — re-export Ask pipeline surface.
- `ai/src/jamly/agent/state.py` (new) — `Citation` + `AskState` pydantic models.
- `ai/src/jamly/agent/ask.py` (new) — `ask.stream` / `ask.cancel` handlers, context + prompt builders, tool-path dispatch, canonical error mapping.
- `ai/src/jamly/agent/checkpoint.py` (new) — `load_ask_state` / `save_ask_state` against the existing `checkpoints` table.
- `ai/src/jamly/agent/tools.py` (new) — `ToolSpec` registry + read-only `search_history` tool with `mutates` gate.
- `ai/src/jamly/bridge.py` (modify) — `ask_handlers(...)` factory; `TaskRegistry.cancel_thread(..., exclude_request_id=...)` excludes the requesting handler from sibling count.
- `ai/src/jamly/agent/chat.py` (modify) — `handle_chat_cancel` passes `exclude_request_id`.
- `tests/unit/test_ask_context.py`, `tests/unit/test_ask_tools.py`, `tests/unit/test_ask_checkpoint.py`, `tests/unit/test_ask_handler.py`, `tests/integration/test_ask_stream.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [x] Ask answers use a bounded rolling transcript context and identify source utterance IDs.
- [x] Graph checkpoints are isolated by meeting/thread ID and recover after restart.
- [x] Tool calls are observable as events and read-only tools cannot mutate meeting state.
- [x] Cancellation, empty context, provider error, and prompt overflow are handled deterministically.
- [x] Recorded/fake model tests validate behavior without mocking the graph into a tautology.

## Definition of Done

- [x] Ask handler tests, checkpoint tests, tool registry tests, integration round-trip tests, changelog entry, `verify-jam-0011` recipe, and CI are complete.

## Escalation rules

- Stop for new tool side effects, network calls, or schema changes and ping owners.

## Verification

```bash
just verify-jam-0011
```
