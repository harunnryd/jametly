---
id: JAM-0013
title: Document OCR and image context pipeline
status: blocked
type: feat
priority: P1
labels: [ocr, capture, ai]
milestone: m5-vision-and-history
assigned-to: unassigned
---

## Blocked by

- JAM-0005 — safe screenshot/blob capture.
- JAM-0006 — local model configuration.
- JAM-0011 — agent tool boundary.

## Context

Meeting recall often depends on slides, whiteboards, and documents that audio alone cannot capture. This task adds the tempfile-based image input path, typed OCR mode selection, and local Marker/VLM fallback boundary. It depends on JAM-0005, JAM-0006, and JAM-0011.

## Scope: files to touch

- `ai/src/jamly/capture.py` (new) — image path validation and cleanup.
- `ai/src/jamly/ocr.py` (new) — typed-content, handwriting, and auto OCR adapters.
- `ai/src/jamly/agent/tools.py` (modify) — expose read-only image context.
- `tests/unit/test_ocr.py`, `tests/integration/test_ocr_image.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] Only approved local paths under the blob directory are readable by OCR.
- [ ] Typed, handwriting, and auto modes map to the documented processing path.
- [ ] Successful output is Markdown with page/region provenance where available.
- [ ] Parser failure and unreadable images map to `OCR_FAILED` without leaking file contents.
- [ ] Large files are cleaned up after processing and deterministic fixtures avoid model downloads.

## Definition of Done

- [ ] Security/path tests, OCR fixtures, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for VLM/model dependency changes, file-permission changes, or schema changes.

## Verification

```bash
just verify-jam-0013
```
