---
id: JAM-0016
title: Transcript and meeting export formats
status: blocked
type: feat
priority: P1
labels: [export, meetings, files]
milestone: m6-release-readiness
assigned-to: unassigned
---

## Blocked by

- JAM-0009 — persisted meeting transcript.
- JAM-0012 — structured summaries and action items.

## Context

The north-star recall test requires transcripts that users can revisit outside the app. This task implements Markdown, JSON, SRT, WebVTT, and PDF export with deterministic timestamps, provenance, and safe output paths. It depends on JAM-0009 and JAM-0012; the dashboard is not required.

## Scope: files to touch

- `ai/src/jamly/meetings/exporters/` (new) — format-specific exporters and shared model.
- `ai/src/jamly/meetings/__init__.py` (modify) — export orchestration and `meeting.export` method.
- `tests/unit/test_exporters.py`, `tests/integration/test_exports.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] All five formats export the same meeting content with stable ordering and timestamps.
- [ ] Meeting stop writes the default Markdown transcript to `~/.config/jametly/transcripts/<date>.md` exactly as required by `GOAL.md`.
- [ ] SRT/WebVTT timing handles overlaps, empty text, and millisecond rounding deterministically.
- [ ] PDF generation is optional and returns a typed unavailable error when dependencies are absent.
- [ ] Output paths are confined to the user-selected export directory and cannot escape it.
- [ ] Export failures do not mutate stored meeting data and are retryable.

## Definition of Done

- [ ] Golden snapshots, path-security tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new binary/document dependencies or security findings and ping owners.

## Verification

```bash
just verify-jam-0016
```
