---
id: JAM-0014
title: Invisible hotkey overlay and typed bridge client
status: in_progress
type: feat
priority: P0
labels: [ui, overlay, tauri, chat]
milestone: m5-vision-and-history
assigned-to: harunnryd
pr: https://github.com/harunnryd/jametly/pull/15
---

## Blocked by

- ~~JAM-0002 — event-capable bridge.~~ merged.
- ~~JAM-0010 — streaming chat method.~~ merged.
- ~~JAM-0011 — Ask workflow.~~ merged.

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

- [x] Overlay opens by the configured global shortcut and stays hidden when idle.
- [x] User input invokes `chat.stream`, renders ordered tokens, and handles done/error/cancel states.
- [x] The typed client maps the Rust `chat_stream_chunk` event and the full-duplex IPC stream to one frontend event model. **Corrected:** no `chat_stream_chunk` event exists — `lib.rs` forwards the sidecar's `event.method` verbatim, so the real surface is `stream.event`, and the client unifies `chat.*` / `ask.*` / bare kinds onto one model.
- [~] Window dimensions, focus, transparency, and accessibility behavior are stable on macOS, Windows, and Linux CI smoke paths. Dimensions/transparency/accessibility are covered; **focus is not stable on macOS** (`focusable: false` is broken — tauri#14102) and global shortcuts **cannot** work on Wayland (no protocol; tao disables the thread). Both report honestly rather than silently failing. The macOS `NSPanel` fix belongs to JAM-0017.
- [x] Typed bridge rejects malformed events and cleans up listeners on unmount.
- [x] E2E tests assert user-visible behavior, not CSS implementation details. Renderer-level journeys only — see the note below.

## Definition of Done

- [x] UI tests (43 frontend + 13 Rust), accessibility review, coverage/format gates, changelog, recipe, and CI are complete.
- [x] **CodeRabbit review on PR #15 addressed.** Seven threads replied with commit-linked resolutions:
  - 3835515760 (block repeat submit) — rejected with cancel-then-supersede rationale.
  - 3835515772 (`state: "timeout"` drop) — fixed in `useChatStream` rewrite.
  - 3835515775 (reset `active.current`) — fixed: ref replaced by `Flight` struct.
  - 3835515777 (bound `jamly_invoke`) — fixed: 30 s `withDeadline` in `bridge.ts`.
  - 3835515782 (Wayland tray lie) — soft-fixed: honest description, hard fallback deferred to JAM-0017.
  - 3835515785 (monitor under cursor) — fixed in `window.rs::resolve_monitor`.
  - 3835515789 (focus before hiding) — fixed: `set_focus()` after `show()`, `toggle_decision` truth table.
- [ ] **Packaged Tauri E2E is deferred, not delivered.** `tauri-driver` has no macOS support, and the only cross-platform path (`@wdio/tauri-service` embedded provider) runs an HTTP WebDriver server inside the shipping binary and adds `wdio:*` capability entries. That is an RCE surface in a product that markets itself as fully local, and a cold release build blows the 12-min `verify-ci` budget on its own. Needs `@security-owner` + `@ipc-owner` sign-off against ADR-0006; tracked as a follow-up.

## Escalation rules

- Stop for new Tauri plugins, entitlements, or OS-specific window APIs and ping owners.

## Owner decisions taken in this task

- `tauri-plugin-global-shortcut` (Cargo) enabled — the canonical and only supported v2 path; `@tauri-apps/plugin-global-shortcut` was already in `package.json`, so this closes a pre-approved gap. Registered in Rust, so no `global-shortcut:*` ACL entries are needed.
- `src-tauri/capabilities/default.json` created. There was no capability file at all, which means the ACL was denying every `invoke`. Permissions are enumerated individually, not `core:default` alone.
- `src-tauri/entitlements.plist` created — already referenced by `bundle.macOS.entitlements`, previously missing, breaking macOS bundle builds. No new TCC entitlement is required for hotkeys.
- macOS `NSPanel` / non-activating overlay **not** taken here; it is squarely "OS-specific window APIs" and JAM-0017 reserves the reusable macOS crate.

## Verification

```bash
just verify-jam-0014
```

## Current status (2026-08-22)

- PR #15 open against `main`: <https://github.com/harunnryd/jametly/pull/15>.
- All seven CodeRabbit threads replied; no outstanding reviews.
- `just verify` green locally (43 frontend + 13 Rust + 103 sidecar integration); CI run for the latest push is green on macOS, Linux, and Windows after the cross-platform test fixes (SIGTERM exit code, stderr polling).
- `status: in_progress` until PR #15 merges; flips to `done` post-merge per the JAM-0011 convention.
