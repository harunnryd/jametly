---
status: accepted
date: 2026-08-20
---

# 0005 — No license tier, no "Pro" gate, no telemetry

## Context and problem statement

Many consumer desktop AI tools ship a "Pro" tier that gates capabilities behind a paid license key, sometimes bundled with telemetry. Should jametly?

## Decision drivers

- The "privacy-first" promise is the product. Telemetry of any kind contradicts the product's stated purpose. Even "anonymized usage stats" creates the appearance of tracking.
- A licensed tier adds a paywall, a license-key flow, a keychain integration, a checkout, and an entitlement engine — all engineering effort that does not contribute to user value.
- The previous prototype (the predecessor codebase in the monorepo) shipped with license-gated move-window shortcuts + PostHog analytics + a proprietary "Pluely API" paid catalog. The product suffered from it: the license gate confused users about what features were free, and the PostHog permission disclosure became a recurring 1-star review theme.
- The competitor research repo (`natively-cluely-ai-assistant`) shipped a "Natively Pro" tier + Natively API gateway + PaywallManager + Personal Use Source License. Every one of those decisions creates 1-star-review surface for "where is my data going".

## Considered options

**A. OSS-only.** Everything free. No license key. No telemetry. No "Pro". Users provide their own LLM keys; we just store them in the OS keychain.

**B. Hybrid OSS core + opt-in Pro tier.** Free core, paid premium models, paid curated prompt library. Stripe/Paddle, not crypto.

**C. Fully commercial.** Closed-source product.

## Decision outcome

Chosen option: **A — full OSS, zero license tier, zero telemetry.**

OSS-only is the simplest and the most honest. Anyone can read the code, modify it, redistribute it. Users pay for LLM API usage directly to OpenAI / Anthropic / etc. — we don't process payments, store customers, or risk 1-star reviews about "where is my data going".

### Architectural lines (will never change)

- No cloud calls from jametly at all. LLM/STT/OCR inference runs locally or against user-configured endpoints with their keys.
- No "jametly has joined the meeting" notification of any kind.
- No telemetry, analytics, crash reports, or remote pings.
- No license key, no license check, no "Pro" feature gating.

(See `docs/decisions/0004-mit-license.md` for license and `SECURITY.md` for the privacy posture.)

### Consequences

- **Good:** zero 1-star reviews about telemetry. Zero license-reset confusion. Every feature works on day one.
- **Good:** contributors can verify the privacy claim by reading the code.
- **Bad:** no recurring revenue stream. We accept this — the goal is wide, free adoption, not profit.
- **Bad:** no paid curated model catalog. Users bring their own provider keys. Documented in `docs/` instead.

## If we ever want a paid tier (guardrail, not plan)

If a paid tier ever happens, it would be:
- Hosted convenience services (e.g. "we host your personal LLM proxy"), NOT core-features
- Strictly opt-in, with a separately-installed binary
- Bypass-able by `uv install jamly-oss` which we ALSO publish

This is a guardrail, not a plan. Most likely we never revisit this decision.

## References

- prior prototype license-gated move-window: `src-tauri/src/shortcuts.rs::set_license_status` (now removed in v2)
- prior prototype PostHog analytics: `src-tauri/src/lib.rs:55-67` (the `tauri-plugin-posthog` init block — not present in v2)
- `natively-cluely-ai-assistant` post-mortem: 4 layers of license/keychain/PaywallManager complexity, "Natively Pro" feature gates, Personal Use Source License — every one of which costs the project research goodwill.
