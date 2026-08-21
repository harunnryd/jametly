---
id: JAM-0014
title: Invisible hotkey overlay and typed bridge client
status: blocked
type: feat
priority: P0
labels: [ui, overlay, tauri, chat]
milestone: m5-vision-and-history
assigned-to: unassigned
---

## Blocked by

- JAM-0002 — event-capable bridge.
- JAM-0010 — streaming chat method.
- JAM-0011 — Ask workflow.

## Context

The frontend is currently a placeholder, so users cannot invoke Ask mode or see streamed answers. This task creates the first usable 600x54 overlay, a typed Tauri bridge client, keyboard focus behavior, and event rendering while preserving the invisibility requirement when idle. It depends on JAM-0002, JAM-0010, and JAM-0011.

## Scope: files to touch

- `app/src/main.tsx`, `app/src/App.tsx` (new) — window dispatch and overlay shell.
- `app/src/lib/bridge.ts` (new) — typed invoke/event wrapper.
- `app/src/components/` (new) — input, stream, status, and error views.
- `src-tauri/src/window.rs`, `shortcuts.rs`, `lib.rs` (new/modify) — overlay lifecycle and hotkeys.
- `app/src/__tests__/` and `tests/e2e/` (new) — behavior and packaged-app flows.
- `package.json`, lockfile, `justfile`, `CHANGELOG.md` (modify).

## Acceptance Criteria

- [ ] Overlay opens by the configured global shortcut and stays hidden when idle.
- [ ] User input invokes `chat.stream`, renders ordered tokens, and handles done/error/cancel states.
- [ ] The typed client maps the Rust `chat_stream_chunk` event and the full-duplex IPC stream to one frontend event model.
- [ ] Window dimensions, focus, transparency, and accessibility behavior are stable on macOS, Windows, and Linux CI smoke paths.
- [ ] Typed bridge rejects malformed events and cleans up listeners on unmount.
- [ ] E2E tests assert user-visible behavior, not CSS implementation details.

## Definition of Done

- [ ] UI tests, packaged Tauri E2E, accessibility review, coverage/format gates, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for new Tauri plugins, entitlements, or OS-specific window APIs and ping owners.

## Verification

```bash
just verify-jam-0014
```
