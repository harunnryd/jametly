---
id: JAM-0012
title: Meeting summaries action items and follow-ups
status: in_progress
type: feat
priority: P1
labels: [meetings, agent, export]
milestone: m4-assistant
assigned-to: harunnryd
---

## Blocked by

- ~~JAM-0009 — persisted meeting sessions.~~ merged.
- ~~JAM-0011 — grounded agent graph.~~ merged (`c950a18`).
- ~~JAM-0010 — streaming LLM provider boundary.~~ merged (`eeffc8c`, `ef26466`).

## Context

The recall test requires more than raw transcription: users need decisions, action items, owners, and follow-ups extracted from a completed meeting. This task adds structured summary and action-item extraction with source citations and explicit uncertainty. It depends on JAM-0009, JAM-0010, and JAM-0011.

## Scope: files to touch

- `ai/src/jamly/meetings/summarizer.py` (new) — structured meeting summary.
- `ai/src/jamly/meetings/extractor.py` (new) — action-item extraction with source IDs.
- `ai/src/jamly/meetings/__init__.py` (modify) — post-process orchestration.
- `tests/unit/test_summarizer.py`, `tests/unit/test_extractor.py`, `tests/integration/test_followups.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [x] Summary output has stable typed fields for decisions, risks, questions, and action items.
- [x] Every extracted action item includes source utterance IDs or an explicit unknown-source marker.
- [x] Follow-up events distinguish question, contradiction, action, and todo kinds.
- [x] An empty/short/noisy fixture produces empty evidence arrays and no unsupported action items.
- [x] Deterministic fixtures cover malformed model output and retry behavior.

## Definition of Done

- [x] Structured-output tests, quality fixtures, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new model/provider dependencies or ungrounded side effects; ping owners.

## Verification

```bash
just verify-jam-0012
```
