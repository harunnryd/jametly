---
status: accepted
date: 2026-08-20
---

# 0006 — Honest macOS stealth disclosure in SECURITY.md

## Context and problem statement

On macOS 15+ Sequoia and macOS 26 Tahoe, Apple deliberately routes all modern screen capture through `ScreenCaptureKit` (SCKit), which captures the post-composition framebuffer regardless of `NSWindowSharingNone`. The legacy flag is bypassed by Zoom, Meet, Teams, Discord, OBS 30+, Loom, FaceTime, and AirPlay on modern macOS.

If jametly silently inherits the previous prototype's marketing, we mislead users. If jametly ships a fake "stealth" claim (e.g. pretending private API calls can do what Apple policy forbids), we publish snake oil and earn the resulting 1-star reviews.

What should we do?

## Decision drivers

- Apple's policy is deliberate, not a bug. It will not change in macOS 27 or later (per Apple developer-forums staff confirmation in 2024).
- Promise less, deliver more. The honest statement of capability is the most defensible position over years.
- Privacy-first product means we don't blame the user when SCKit captures us; we tell them honestly what we do and don't do.
- For users whose threat model is "screen recorder" → we offer no false protection; we offer honest Band A + Band B (default) + Band C opt-in detection.

## Considered options

**A. Silent.** Don't mention macOS capture. Ship the same false promise as the previous prototype.

**B. Half-disclose.** Vague language: "macOS may capture the window in some configurations."

**C. Full disclosure.** Explicit statement of what each tier blocks and what doesn't; an opt-in Band C (SCKit self-probe detection) that responds but does not prevent; documented limitation that "no third-party app can guarantee invisibility to a co-resident SCKit recorder on macOS".

**D. Add private API workaround.** Try to use `CGWindowListCreateImage` interception or similar. App Store hostile; Apple policy hostile; not portable to macOS 26+.

## Decision outcome

Chosen option: **C — full disclosure in `SECURITY.md`**, with three documented tiers:

| Band | Default | What it blocks | What it doesn't block |
|---|---|---|---|
| 0 | yes (`content_protected: true`) | Legacy `CGWindowListCreateImage` path: `xcap`, `screencapture -x`, older OBS, AirPlay on older macOS | `ScreenCaptureKit`-based recorders (Zoom, Meet, Teams, Discord, OBS 30+, Loom, FaceTime, modern AirPlay) |
| 1 | yes (in CI) | Same as Band A + CI verification on every release | Same |
| 2 | opt-in (default off) | Band A + Band B + a low-resolution SCKit self-probe that detects co-resident capture sessions and obscures the overlay within ~500 ms | None — this is detection + response, not prevention |

### The honest statement

> No third-party app — including jametly — can guarantee that its window is invisible to a screen recorder that has been granted Screen Recording permission on macOS. Starting with macOS 15 Sequoia, `ScreenCaptureKit` composes window contents into a post-composition framebuffer before capture, intentionally bypassing the legacy `NSWindowSharingNone` flag. Apple has confirmed this is a deliberate platform policy. jametly ships the strongest public guarantee available (Band A + Band B by default). Users should not rely on the app to keep on-screen content hidden from any user who has been granted Screen Recording permission.

This text lives verbatim in `SECURITY.md`.

### Consequences

- **Good:** the privacy claim is defensible. We are not selling false protection.
- **Good:** Band C (opt-in SCKit detection) becomes a feature we can ship without misleading.
- **Good:** any future Apple policy change that loosens the constraint can be communicated honestly without rewriting marketing.
- **Bad:** some users will want the "guaranteed invisible" experience and will be disappointed. Those users should not be jametly users.
- **Bad:** the previous prototype marketed false stealth; consumers searching for that capability may land on a successor project that we are not. Acceptable.

## References

- Tauri issue confirming macOS 15+ SCKit behaviour: https://github.com/tauri-apps/tauri/issues/14200
- Electron issue (same problem, closed as not planned): https://github.com/electron/electron/issues/48258
- Apple ScreenCaptureKit docs: https://developer.apple.com/documentation/screencapturekit/
- WWDC23 10136 "What's new in ScreenCaptureKit": https://developer.apple.com/videos/play/wwdc2023/10136/
- Addpipe blog: "Screen Sharing Got Smarter on macOS": https://blog.addpipe.com/screen-sharing-got-smarter-and-more-private-on-macos-understanding-the-system-private-window-picker/
- Tauri issue #14200 status thread (upstream unaddressed as of 2026-08)
