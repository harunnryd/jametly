---
id: JAM-0017
title: Stealth window lifecycle and honest macOS disclosure
status: blocked
type: feat
priority: P1
labels: [stealth, macos, windows, platform]
milestone: m6-release-readiness
assigned-to: unassigned
---

## Blocked by

- JAM-0014 — overlay and window application shell.
- Security owner review for platform-specific behavior.

## Context

jametly must remain invisible when idle while being honest about the limits of macOS ScreenCaptureKit. This task hardens window creation, dock/taskbar behavior, content protection, global shortcuts, and cleanup across supported desktop platforms. It depends on JAM-0014 and the existing stealth decision.

## Scope: files to touch

- `src-tauri/src/window.rs`, `shortcuts.rs` (new) — window and shortcut lifecycle.
- `core/stealth-macos/src/lib.rs` (new, only if the approved macOS implementation requires a reusable core crate) — documented public/private API boundary.
- `src-tauri/tauri.conf.json`, capabilities, entitlements (modify only with approval).
- `tests/e2e/stealth.spec.ts`, `tests/stealth/` (new).
- `docs/decisions/0006-macos-stealth-honest-disclosure.md` and `CHANGELOG.md` (modify if behavior changes).

## Acceptance Criteria

- [ ] Idle app has no visible overlay, dock/taskbar affordance, or focused window.
- [ ] Configured shortcut opens/closes the overlay reliably and releases on shutdown.
- [ ] Content protection and platform limitations match the documented security disclosure.
- [ ] Permission denial and unsupported platform paths fail visibly to the user without false stealth claims.
- [ ] Stealth tests are gated appropriately and do not assert framework CSS internals.

## Definition of Done

- [ ] Platform review, security disclosure, E2E, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for entitlements, private APIs, or security behavior changes and ping `@security-owner`.

## Verification

```bash
just verify-jam-0017
```
