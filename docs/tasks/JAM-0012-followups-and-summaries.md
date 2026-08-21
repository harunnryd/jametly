---
id: JAM-0012
title: Meeting summaries action items and follow-ups
status: blocked
type: feat
priority: P1
labels: [meetings, agent, export]
milestone: m4-assistant
assigned-to: unassigned
---

## Blocked by

- JAM-0009 — persisted meeting sessions.
- JAM-0011 — grounded agent graph.
- JAM-0010 — streaming LLM provider boundary.

## Context

The recall test requires more than raw transcription: users need decisions, action items, owners, and follow-ups extracted from a completed meeting. This task adds structured summary and action-item extraction with source citations and explicit uncertainty. It depends on JAM-0009, JAM-0010, and JAM-0011.

## Scope: files to touch

- `ai/src/jamly/meetings/summarizer.py` (new) — structured meeting summary.
- `ai/src/jamly/meetings/extractor.py` (new) — action-item extraction with source IDs.
- `ai/src/jamly/meetings/__init__.py` (modify) — post-process orchestration.
- `tests/unit/test_summarizer.py`, `tests/integration/test_followups.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] Summary output has stable typed fields for decisions, risks, questions, and action items.
- [ ] Every extracted action item includes source utterance IDs or an explicit unknown-source marker.
- [ ] Follow-up events distinguish question, contradiction, action, and todo kinds.
- [ ] An empty/short/noisy fixture produces empty evidence arrays and no unsupported action items.
- [ ] Deterministic fixtures cover malformed model output and retry behavior.

## Definition of Done

- [ ] Structured-output tests, quality fixtures, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new model/provider dependencies or ungrounded side effects; ping owners.

## Verification

```bash
just verify-jam-0012
```
