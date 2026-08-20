# jametly — GOAL

> The mission, the architectural lines, the non-goals, and the north-star test.
> For install + quickstart, see [`README.md`](./README.md). For the rationale behind each architectural line, see `docs/decisions/0001..NNNN`. For the threat model and capability envelope, see [`SECURITY.md`](./SECURITY.md).

---

## Mission

**jametly is a local, invisible, on-device AI that listens to your meetings and remembers the parts you'll want to revisit — without you, your participants, or your machine ever talking to the cloud.**

Three load-bearing words: **local**, **invisible**, **useful**. A change that violates any of the three is not a change to jametly; it's a different project.

## Problem

Live meetings move fast — by the time you reach for a notepad, the decision you're trying to capture is already past you. Every existing AI meeting assistant solves this with a cloud round-trip and a "this bot has joined the call" notification, which is fine for the assistant vendor and a non-starter for anyone who needs the conversation to stay private.

## Solution

jametly runs Whisper and a local LLM on the user's machine. It captures system audio through the OS-native loopback path, transcribes and reasons locally, and surfaces answers, summaries, and follow-ups in a hotkey overlay. There is no server. There is no bot. There is no "jametly has joined the meeting" alert.

## Architectural lines — will never change

These are the immutables. A PR that violates one of these is a PR against a different project.

- **No cloud calls from jametly at runtime.** Your audio, your transcripts, and your meeting notes never leave your machine. Network egress from the app is limited to model downloads from upstream providers (Ollama, OpenAI, Anthropic, etc.) configured by the user with their own keys. See [`SECURITY.md`](./SECURITY.md) §"Privacy posture" for the precise boundary.
- **No "bot has joined the meeting" notification.** jametly is a passive listener on system audio. It never registers as a meeting participant.
- **No telemetry, analytics, crash reports, or remote pings.** No analytics SDK, no Sentry, no PostHog, no "anonymous usage stats," no `?v=1` pings. If jametly crashes, the user finds out because the app stopped working — not because we did.
- **No license key, no Pro tier, no feature gating.** Every feature of jametly is free, in the binary, on day one. Users pay for LLM API usage directly to the provider they chose. We never process payment, never store a customer record, never gate a feature behind a checkout.
- **Honest macOS disclosure.** On macOS 15 Sequoia and later, Apple routes all modern screen capture through `ScreenCaptureKit`, which bypasses `NSWindowSharingNone`. jametly will never claim invisibility against a co-resident SCKit recorder; the strongest available public guarantee ships by default. See [`SECURITY.md`](./SECURITY.md) §"macOS stealth".

## Non-goals — currently out of scope

These are *not* promises that we'll never do them. They are not-in-scope *today*. Each has an ADR or a roadmap note; check before assuming "no".

- **Live translation between languages.** Planned for v0.4.
- **Speaker diarization beyond simple A/B routing.** Planned for v0.5.
- **Mobile (iOS / Android).** No plans. Desktop loopback capture is the reason the app works; the mobile audio model is different and is its own project.
- **Enterprise SSO, audit logs, role-based access.** jametly is a personal-tool project, not an enterprise product.
- **Hosted "jametly Cloud" convenience service.** If it ever happens, it ships as a separate, opt-in binary that bypasses to `uv install jametly-oss` — see `docs/decisions/0005-no-license-tier.md` §"If we ever want a paid tier (guardrail, not plan)".

## North-star test

We measure success by **two observable behaviors**, both testable in a 90-minute session on a clean install:

1. **Invisibility test.** A person looking at the user's screen for thirty seconds during a call cannot tell jametly is running. No dock icon. No overlay when not invoked. No process name in the menu bar. No entries in `Activity Monitor` that a non-technical observer would flag.
2. **Recall test.** After a one-hour meeting, the user can name the three action items agreed in the call without opening the app. The transcript saved to `~/.config/jametly/transcripts/<date>.md` matches what the user remembers.

If a release passes both tests, the release is on-mission regardless of which model is in use, which platform shipped, or how many features landed. If a release passes neither, no amount of new features recovers it.

## What this document is not

- Not a roadmap. Roadmap is `docs/roadmap/`.
- Not a security threat model. That is [`SECURITY.md`](./SECURITY.md).
- Not a code-style guide. That is [`STYLE.md`](./STYLE.md).
- Not a contribution policy. That is [`CONTRIBUTING.md`](./CONTRIBUTING.md).
- Not a rationale. Each architectural line has an ADR in `docs/decisions/` for the *why*.

## How to change this file

You almost never should. The architectural lines are the immutables. If you genuinely need to change one:

1. Open an issue using `.github/ISSUE_TEMPLATE/goal-change.md`.
2. Write an ADR in `docs/decisions/` with status `proposed`.
3. Get a maintainer ack in the issue, then merge the ADR and this file in the same PR.

A change to the **mission statement**, the **architectural lines**, or the **north-star test** requires a `major:` commit subject (Conventional Commits) and a `CHANGELOG.md` entry.

## Status

v0.x — accepted. Under active development; architectural lines frozen. Source of truth for the architectural lines lives here. `SECURITY.md` and `docs/decisions/` link back; they do not duplicate.
