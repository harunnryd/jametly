# Security policy

## Reporting a vulnerability

**Email:** security@jametly.app (PGP key: see `https://jametly.app/.well-known/pgp-key.asc`; mirror in `LICENSE` for offline verification)

Please **do not** file a public GitHub issue for security-sensitive bugs. We aim to acknowledge within 48 hours and ship a fix within 90 days under coordinated disclosure.

Include in your report:

- Affected version / commit SHA
- Reproduction steps (or a PoC)
- Platform affected (macOS 13/14/15/26+ or Windows 11 or Linux distro + version)
- Impact assessment (data exposure, code execution, privilege escalation, etc.)

## Supported versions

| Version | Supported |
|---|---|
| `main` branch | yes |
| latest release | yes |
| previous release | yes (security fixes only) |
| anything older | no |

## Threat model — what's in scope

jametly is a desktop AI assistant that **listens to your system audio** and **runs AI inference locally**. The threat model assumes:

- The user's machine is trusted
- The user's microphone and system-audio input may be from adversarial meeting participants
- The user's filesystem is shared (other apps may read its config)
- Network egress is untrusted (audio must NOT leak)
- Any code an AI agent runs (in Python or Rust) has the user's privileges

### In-scope concerns

- IPC privilege escalation (Rust ↔ Python bridge)
- Audio data exfiltration (silent cloud calls, telemetry paths)
- Prompt injection through meeting audio causing unintended tool calls
- Local file access beyond declared capability
- Auto-update integrity (signature verification, downgrade protection)
- Keychain / DPAPI credential storage
- macOS / Windows / Linux privilege boundaries
- Stealth / overlay capture assumptions (see "macOS caveat" below)

### Out-of-scope concerns

- Hallucinations, model errors, or jailbreak of the underlying LLM
- Speech recognition of the user's own voice (transcription quality issues)
- Adversarial physical access to the device
- Third-party library CVEs in transitive deps (we patch; we don't own)

## macOS stealth — the honest limit

> jametly's window uses `content_protected: true` which sets `NSWindowSharingNone` on macOS. This blocks the legacy `CGWindowListCreateImage` capture path used by `xcap`, the `screencapture -x` CLI, older OBS versions, and AirPlay mirroring on older macOS.

**It does NOT block `ScreenCaptureKit`-based capture** used by Zoom, Google Meet, Microsoft Teams, Discord, OBS 30+, Loom, FaceTime, and AirPlay on macOS 15+. Apple deliberately routes all modern capture through the post-composition framebuffer, bypassing `NSWindowSharingNone`. This is an Apple platform policy, not a jametly limitation.

**You should not rely on jametly to keep on-screen content hidden from any user who has been granted Screen Recording permission, or any screen-share session the user joins intentionally.** macOS provides no platform mechanism for that guarantee, and we will not pretend otherwise.

A future opt-in "Stealth Mode" (Band C in the ADR-0006 tier table) will detect co-resident SCKit capture sessions targeting the window and obscure the UI to a placeholder within ~500 ms. This is **detection + response**, not prevention.

Full disclosure rationale: `docs/decisions/0006-macos-stealth-honest-disclosure.md`.

## Privacy posture — architectural lines (will never change)

- **No telemetry.** No analytics SDK, no crash reporter, no remote ping of any sort.
- **No "joined the meeting" notification.** jametly does not register as a participant.
- **Local-only LLM/STT/OCR inference.** Network calls are limited to model downloads from upstream providers' APIs (Ollama, OpenAI, Anthropic, etc.) configured by the user with their own keys.
- **API keys in OS keychain** (macOS Keychain, Windows Credential Manager, libsecret on Linux). Never in plaintext config files.
- **`ts` never escape the host machine.** Trusted timing: files in app data dir, SQLite in app data dir, no remote storage.

## Safe harbor

We commit to not pursuing legal action against researchers who:

- Make a good-faith effort to avoid privacy violations
- Avoid exploiting any vulnerability beyond what is necessary to demonstrate it
- Give us a reasonable time to fix before public disclosure
- Do not violate any other applicable laws in the course of their research
