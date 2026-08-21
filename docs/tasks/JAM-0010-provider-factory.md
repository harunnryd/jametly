---
id: JAM-0010
title: Local LLM provider factory and streaming chat method
status: blocked
type: feat
priority: P0
labels: [llm, providers, chat, ai]
milestone: m4-assistant
assigned-to: unassigned
---

## Blocked by

- JAM-0002 — streaming event transport.
- JAM-0003 — async runtime and cancellation.
- JAM-0006 — provider configuration and secure credentials.

## Context

jametly needs a controlled local LLM boundary for answers and summaries. This task adds provider selection, model construction, and `chat.stream`/`chat.cancel` without embedding provider-specific behavior in the bridge or UI. Meeting-context integration belongs to the Ask graph task. It depends on JAM-0002, JAM-0003, and JAM-0006.

## Scope: files to touch

- `ai/src/jamly/llm/__init__.py` (new) — provider factory and validated model settings.
- `ai/src/jamly/llm/curl_model.py` (new) — user-supplied cURL-compatible provider adapter if approved.
- `ai/src/jamly/agent/` (new) — minimal streaming chat handler and cancellation registry.
- `tests/unit/test_llm_factory.py`, `tests/integration/test_chat_stream.py` (new).
- `justfile`, `CHANGELOG.md`, and task docs (modify).

## Acceptance Criteria

- [x] Provider selection is explicit, persisted in local `config.toml`, and defaults to the documented local model.
- [x] `providers.list` returns configured AI/STT providers and `providers.set_selected` persists the selected provider through the config boundary.
- [x] `chat.stream` emits ordered token/state/done/error events with correlation IDs.
- [x] `chat.cancel` stops an in-flight stream without corrupting the meeting transcript.
- [x] Long-running requests enforce the configured deadline and emit canonical `PYTHON_TIMEOUT` errors.
- [x] Missing credentials, unavailable model, rate limit, and malformed provider responses map to canonical errors.
- [x] Tests use deterministic fake models; no runtime network call is required by CI.

## Definition of Done

- [x] Provider/security review, tests, coverage, changelog, recipe, and CI are complete.

## Escalation rules

- Stop for a new runtime provider dependency or cloud-default behavior; ping tooling/security owners.

## Verification

```bash
just verify-jam-0010
```
