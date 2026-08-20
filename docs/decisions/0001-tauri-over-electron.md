---
status: accepted
date: 2026-08-20
---

# 0001 — Tauri 2 over Electron for the desktop shell

## Context and problem statement

jametly is a desktop AI overlay that must stay invisible during meetings. Constraints: small binary footprint, low memory at idle, no telemetry, fast startup on cold boot, full OS-level stealth primitives (content-protected windows, native loopback audio, global shortcuts). Both Tauri 2 (Rust + WebView) and Electron (Node + Chromium) are viable. Which one?

## Decision drivers

- Bundle size matters: a multi-GB installer is a non-starter for a personal-tool aesthetic.
- Cold start matters: a 4-second Electron startup defeats the "instant overlay" promise.
- Native OS integration matters: content-protection, audio loopback, NSPanel styling.
- Stealth requires predictable, narrow-window native code paths; Chromium's footprint complicates that.
- Single-binary distribution (no Node runtime required on user machine).

## Considered options

**Tauri 2 + WebView (system WebKit / WebView2 / WebKitGTK).** ~10 MB base binary; Rust host for native code; system WebView means we don't ship a browser.

**Electron 30 + Node 22.** ~150 MB base; Chromium for every install; mature ecosystem and many more examples; faster initial development velocity.

**Native SwiftUI / WinUI / GTK 4.** Best per-OS fit, but ~3× the development cost and zero cross-platform UI code reuse.

## Decision outcome

Chosen option: **Tauri 2**.

Rust owns the side that has to talk to OS-level primitives (audio loopback via cidre/wasapi/libpulse, NSPanel styling via `tauri-nspanel`, content-protection via NSWindowSharingNone). Python owns the AI orchestration side. Frontend is React 19 + Vite 5 inside Tauri's WebView — same components we'd write for Electron, shipped in a fraction of the binary.

### Consequences

- **Good:** small binary, fast cold-start, narrow native attack surface, single Rust+Python+JS toolchain on the user's machine.
- **Good:** bypassing Electron's renderer sandbox lets us design stealth primitives exactly to spec.
- **Good:** the research reference (`natively-cluely-ai-assistant`, an Electron competitor in this monorepo) gave us a clear "what to skip" list.
- **Bad:** Tauri 2 has rougher edges than Electron (window APIs); some patterns require workarounds (`tauri-nspanel` for NSPanel, hand-rolled `WS_EX_NOACTIVATE` on Windows).
- **Bad:** smaller community; we'll occasionally be the first to hit a bug.

## References

- Tauri 2 docs: https://v2.tauri.app
- `tauri-nspanel`: https://github.com/ahkohd/tauri-nspanel
- `natively-cluely-ai-assistant` reference (this monorepo): Electron competitor from which we borrowed UX patterns and rejected architectural patterns (god-class `LLMHelper.ts`, 349 IPC channels, electron-store unencrypted for BYOK — all `natively` patterns we explicitly avoid).
