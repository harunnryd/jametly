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

- [x] Existing echo and `debug.stream` behavior remains compatible. JAM-0002's `tests/unit/test_sidecar.py` and `tests/integration/test_bridge_events.py` pass unchanged against the async path; manual smoke output is byte-identical.
- [x] Multiple in-flight requests correlate to the correct replies. Covered in-process (25 concurrent) and over the subprocess (10 concurrent).
- [x] Cancellation stops a running handler and emits a deterministic terminal event: one `stream.event` with `kind: "cancelled"` **and** the correlated reply `{"cancelled": true}`, because events are lossy per `docs/architecture/01-ipc.md` backpressure.
- [x] One slow handler cannot block unrelated requests or event delivery. The first implementation failed this over a real pipe — stdin was read on the event loop; `read_line` now offloads it. Caught by `tests/integration/test_bridge_async.py`, not by the StringIO unit tests.
- [x] EOF and malformed input produce typed, testable outcomes. EOF cancels in-flight work deterministically; malformed input keeps JAM-0001's `PARSE_ERROR` with an empty `id`.
- [x] `just verify` and `just verify-ci` pass.

## Definition of Done

- [x] Acceptance criteria checked, tests red-first, coverage not regressed, changelog updated, and PR CI green. **PR #3; matrix green on macOS, Ubuntu, and Windows.**
- [ ] `@ipc-owner` review is requested for any wire-contract change. **Required: this task adds the `cancelled` kind to the `stream.event` taxonomy and the `debug.sleep` diagnostic in `docs/architecture/01-ipc.md`, a file outside the declared scope list. `shared/schemas/ipc/v1.json` is untouched.**

## Escalation rules

- New dependency, IPC schema change, missing tool, or security finding requires the owner escalation rules in `AGENTS.md`.
- Split the task if the runtime and cancellation work exceeds one day.

## Verification

```bash
just verify-jam-0003
```
