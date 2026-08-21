---
id: JAM-0026
title: Cropper window and first-run model provisioning
status: blocked
type: feat
priority: P1
labels: [ui, capture, models, onboarding]
milestone: m5-vision-and-history
assigned-to: unassigned
---

## Blocked by

- JAM-0005 — screen capture and region contract.
- JAM-0006 — local config/provider state.
- JAM-0014 — overlay/window shell.
- JAM-0013 — OCR/image context integration.

## Context

The module map includes a cropper window and the product allows user-configured local model downloads, but neither surface is owned by the current backlog. This task adds a bounded region-selection flow and first-run model readiness UX without making downloads mandatory for CI or silently contacting providers. It must preserve the honest permissions and privacy disclosures.

## Scope: files to touch

- `app/src/pages/cropper.tsx` (new) — region selection and confirmation.
- `app/src/hooks/useModelProvisioning.ts` (new) — explicit download/readiness state.
- `src-tauri/src/capture.rs`, config/model commands (modify).
- `tests/e2e/cropper.spec.ts`, `tests/unit/test_model_provisioning.py` (new).
- `README.md`, `SECURITY.md`, `justfile`, `CHANGELOG.md` (modify).

## Acceptance Criteria

- [ ] Cropper returns a validated region or explicit cancellation without capturing unintended pixels.
- [ ] Model readiness distinguishes installed, downloading, unavailable, and failed states.
- [ ] Downloads require explicit user/provider configuration and expose progress/errors.
- [ ] No model download is required by normal unit, CI, or bridge tests.
- [ ] Permission and privacy messaging matches the documented macOS disclosure.

## Definition of Done

- [ ] Acceptance criteria, permission/security review, tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new permissions, network behavior, model dependencies, or entitlement changes and ping owners.

## Verification

```bash
just verify-jam-0026
```
