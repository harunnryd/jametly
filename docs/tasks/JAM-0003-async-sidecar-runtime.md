---
id: JAM-0003
title: Async Python sidecar runtime and cancellation
status: ready
type: feat
priority: P0
labels: [ai, ipc, concurrency]
milestone: m1-full-duplex-ipc
assigned-to: unassigned
---

## Blocked by

- ~~JAM-0002 — bidirectional IPC events and reply routing.~~ Merged as `5dde2af`.

## Context

JAM-0002 establishes event routing, but the Python sidecar still uses a synchronous stdin loop. Long-running work must not block inbound cancellation, concurrent requests, or event emission. This task introduces the asyncio runtime boundary while preserving the existing wire contract and diagnostic methods. It depends on JAM-0002.

## Scope: files to touch

- `ai/src/jamly/bridge.py` (new) — asyncio reader/writer, request dispatch, cancellation, and stdout serialization.
- `ai/src/jamly/__main__.py` (modify) — start the async runtime and preserve CLI behavior.
- `ai/src/jamly/protocol.py` (modify) — add typed task/cancellation helpers if required by the runtime.
- `tests/unit/test_async_bridge.py` (new) — concurrency, cancellation, ordering, and EOF tests.
- `tests/integration/test_bridge_async.py` (new) — subprocess async request/event round-trip.
- `justfile` (modify) — add `verify-jam-0003`.
- `CHANGELOG.md` (modify) — record the runtime milestone.

## Acceptance Criteria

- [ ] Existing echo and `debug.stream` behavior remains compatible.
- [ ] Multiple in-flight requests correlate to the correct replies.
- [ ] Cancellation stops a running handler and emits a deterministic terminal event.
- [ ] One slow handler cannot block unrelated requests or event delivery.
- [ ] EOF and malformed input produce typed, testable outcomes.
- [ ] `just verify` and `just verify-ci` pass.

## Definition of Done

- [ ] Acceptance criteria checked, tests red-first, coverage not regressed, changelog updated, and PR CI green.
- [ ] `@ipc-owner` review is requested for any wire-contract change.

## Escalation rules

- New dependency, IPC schema change, missing tool, or security finding requires the owner escalation rules in `AGENTS.md`.
- Split the task if the runtime and cancellation work exceeds one day.

## Verification

```bash
just verify-jam-0003
```
