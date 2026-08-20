> **Working tagline** — swap freely. Candidates: *"A second pair of ears, always paying attention."* / *"Show up. We'll handle the rest."*

**Problem.** Live meetings move fast — by the time you reach for a notepad, half the decision is already past you.

**Solution.** jametly runs a local, on-device AI that listens with you, captures the thread, and surfaces the bits you'll want to revisit.

**Differentiator.** 100% local, 100% invisible, 100% yours — no cloud round-trip at runtime, no visible bot, no meeting-join notification.

## What it is

- Listens to system audio on macOS, Windows, and Linux
- Transcribes and reasons locally with a model you control
- Surfaces answers, summaries, and follow-ups in a hotkey overlay
- Speaker-labeled live meeting transcription with smart follow-ups
- Document OCR + "use image" mode (typed-content and handwriting)
- Saved meeting transcripts in MD / SRT / WebVTT / PDF / JSON
- Zero footprint: no window you can see, no dock icon, no "jametly has joined the meeting" alert

## What's in scope

- Local-only transcription and reasoning (`faster-whisper` + a local LLM via Ollama, default `qwen2.5:7b-instruct`). Model downloads go to upstream-provider APIs configured by the user with their own keys — see [SECURITY.md §Privacy posture](./SECURITY.md).
- Hotkey-driven capture of answers, summaries, action items, follow-ups
- A single config file: `~/.config/jametly/config.toml`
- Cross-platform signed installers with auto-update via GitHub Releases

## What's NOT in scope

**Architectural lines (will never change):**

- No cloud calls. Your audio never leaves your machine.
- No bot joins your call. No meeting-join notification of any kind.
- No telemetry, analytics, crash reports, or remote pings.
- No license key, no Pro tier, no feature gating. Every feature is free.

**Currently out of scope (may revisit):**

- Live translation (planned for v0.4)
- Speaker diarization beyond simple A/B routing (planned for v0.5)
- Mobile / iOS / Android (no plans)
- Enterprise SSO or audit logs (this is a personal-tool project)

## On macOS stealth — honest disclosure

On macOS 15 Sequoia and later, Apple deliberately routes all modern screen capture through `ScreenCaptureKit`, which captures the post-composition framebuffer regardless of `NSWindowSharingNone`. This means **no third-party app — including jametly — can guarantee invisibility to a screen recorder that has been granted Screen Recording permission**. jametly's default `content_protected: true` blocks the legacy path (`xcap`, `screencapture`, older OBS). See [SECURITY.md](./SECURITY.md) and [docs/decisions/0006-macos-stealth-honest-disclosure.md](./docs/decisions/0006-macos-stealth-honest-disclosure.md) for the full disclosure.

## Quickstart

```bash
just install          # one-time, ~30s
just verify           # the agent's "did it work?" gate
just dev              # Tauri dev server + Python sidecar
```

For AI coding agents, read [AGENTS.md](./AGENTS.md) before anything else. For the test philosophy, read [docs/conventions/TEST_STRATEGY.md](./docs/conventions/TEST_STRATEGY.md).

## Architecture

See [docs/architecture/00-overview.md](./docs/architecture/00-overview.md) for the single ASCII diagram.

## License

MIT for the code. "jametly" name and logo reserved — see [TRADEMARKS.md](./TRADEMARKS.md).
