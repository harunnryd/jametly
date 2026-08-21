---
id: JAM-0020
title: Optional speech provider fallback chain
status: blocked
type: feat
priority: P2
labels: [stt, providers, ai]
milestone: m3-meeting-memory
assigned-to: unassigned
---

## Blocked by

- JAM-0008 — local STT provider boundary.
- JAM-0006 — provider configuration and secure storage.
- `@tooling-owner` approval for provider client dependencies.

## Context

Local faster-whisper is the default, but the architecture allows explicit OpenAI, Groq, and user-defined cURL-compatible fallback providers. This task adds those optional adapters without weakening the local-only default or making remote calls implicit. It is deliberately separate from the core STT pipeline.

## Scope: files to touch

- `ai/src/jamly/stt/openai_whisper.py` (new) — explicit provider adapter.
- `ai/src/jamly/stt/groq_whisper.py` (new) — explicit provider adapter.
- `ai/src/jamly/stt/custom.py` (new) — validated user-paste cURL adapter.
- `ai/src/jamly/stt/base.py`, config, tests (modify).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [ ] Remote providers are disabled unless explicitly selected by the user.
- [ ] Credentials come only from secure storage and never appear in logs.
- [ ] Retry, auth, rate-limit, timeout, and unavailable errors map to canonical codes.
- [ ] Tests use HTTP fakes and prove no network call occurs for the local default.

## Definition of Done

- [ ] Acceptance criteria, security review, dependency approval, tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for runtime network behavior, new dependencies, or secrets handling and ping tooling/security owners.

## Verification

```bash
just verify-jam-0020
```
