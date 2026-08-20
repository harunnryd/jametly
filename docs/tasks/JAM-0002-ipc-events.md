---
id: JAM-0002
title: Bidirectional event streaming over the stdio bridge
status: in_progress
type: feat
priority: P0
labels: [ipc, bridge, events, ai, rust, infra]
milestone: m1-full-duplex-ipc
assigned-to: unassigned
---

## Blocked by

- None. The project owner approved the additive `Event` schema direction during task planning; the PR must still request the configured IPC CODEOWNER review.

## Context

JAM-0001 established a request/reply JSON-RPC + NDJSON bridge, but the transport currently reads exactly one stdout line per request and parses it as a reply. The IPC architecture also defines fire-and-forget events such as `stream.event`, `transcript.partial`, `audio.level`, and `python.crash`; those events cannot safely cross the current bridge. This task completes the full-duplex IPC spine so later audio, STT, chat, and meeting features can stream data without reimplementing transport logic. See [`docs/decisions/0003-stdio-ipc-over-http.md`](../decisions/0003-stdio-ipc-over-http.md) and [`docs/architecture/01-ipc.md`](../architecture/01-ipc.md).

## Scope: files to touch

- `shared/schemas/ipc/v1.json` (modify) — add the additive `Event` envelope to the canonical IPC schema; requires `@ipc-owner` approval before implementation.
- `core/ipc-proto/src/lib.rs` (modify) — add the Rust `Event` model and wire-message discrimination for requests, replies, and events.
- `core/ipc-proto/Cargo.toml` (modify) — add approved `insta` and `proptest` test dependencies if contract snapshots/property tests are introduced.
- `core/ipc-proto/tests/protocol_contract.rs` (modify) — test event round-trips, envelope discrimination, and typed error replies.
- `ai/src/jamly/protocol.py` (modify) — add the Pydantic `Event` mirror and enforce valid reply shape.
- `ai/src/jamly/__main__.py` (modify) — add method registration and the diagnostic `debug.stream` event emitter.
- `src-tauri/src/bridge.rs` (modify) — route stdout through a background reader, correlate replies by ID, and expose a bounded event channel.
- `src-tauri/src/lib.rs` (modify) — wire the event receiver into the Tauri application boundary without adding frontend rendering.
- `tests/unit/test_sidecar.py` (modify) — cover registry dispatch, event emission, and reply validation.
- `tests/integration/test_bridge_events.py` (new) — verify event ordering and reply correlation through the Python subprocess.
- `justfile` (modify) — add the `verify-jam-0002` recipe.
- `docs/architecture/01-ipc.md` (modify) — document event routing and `debug.stream` as a transport diagnostic method.
- `docs/tasks/JAM-0002-ipc-events.md` (modify) — check acceptance criteria and definition of done as work completes.
- `CHANGELOG.md` (modify) — add the full-duplex IPC milestone under `Unreleased`.

## Explicitly out of scope

- Audio capture, resampling, ring buffers, and `core/audio-backend`.
- Whisper, VAD, diarization, OCR, chat, meeting, and history methods.
- Frontend event rendering or a typed frontend bridge wrapper.
- Crash restart supervision beyond making pipe termination distinguishable.
- Request timeout enforcement and binary tempfile payload handling.
- A full asyncio `ai/src/jamly/bridge.py` rewrite; that belongs in a later task.

## Acceptance Criteria

- [x] `shared/schemas/ipc/v1.json` defines an additive `Event` envelope with `method` and `params`, with `id` absent or `null`, and the top-level schema accepts requests, replies, and events; `@ipc-owner` approval is requested before the schema change.
- [x] `cargo test -p ipc-proto` exits 0; events round-trip, event lines are not parsed as replies, invalid events are rejected, and typed error replies cover all canonical error codes.
- [x] Contract tests include at least one snapshot or property-based invariant, with `@tooling-owner` approval before adding pinned test dependencies.
- [x] `uv run pytest tests/unit/test_sidecar.py -v` exits 0; the method registry routes `echo`, `debug.stream`, and unknown methods, and `Reply` rejects envelopes containing both `result` and `error`.
- [x] `uv run pytest tests/integration/test_bridge_events.py -v` exits 0; `debug.stream` emits ordered `stream.event` messages before the correlated reply, preserving `correlation_id` and ending with `kind: done`.
- [x] `cargo test -p jametly -- --nocapture` exits 0; the Rust bridge surfaces events through its event channel while preserving request/reply correlation and the existing echo behavior.
- [x] The event channel is bounded by a named capacity constant and has an explicit overflow policy; the reader cannot grow an unbounded in-memory event collection.
- [x] `just verify` exits 0.
- [x] `just verify-ci` exits 0 once for CI parity.
- [ ] Coverage thresholds are not regressed: `core/ipc-proto` remains at least 90% line coverage, `src-tauri/` remains at least 70%, and Python coverage remains at or above the configured gate. **Partially met — `core/ipc-proto` 100% (was 100%), Python 95% (was 91.89%, gate 70%), but `src-tauri/` is 67.0% (was 45.0% on `main`). Not regressed — improved 22 points — yet still short of the documented 70%. `src-tauri/src/lib.rs` is 0% because the Tauri command surface needs `tauri::test::mock_app()` + `MockRuntime` per TEST_STRATEGY.md §2b, which requires making commands generic over `R: Runtime`. Flagged for `@tooling-owner`/`@rust-owner`; suggest a follow-up task rather than test-after code here.**
- [x] Manual smoke with `debug.stream` emits the requested event lines followed by a parseable correlated reply:

  ```bash
  printf '%s\n' '{"id":"r1","method":"debug.stream","params":{"count":2}}' | uv run --project ai python -m jamly
  ```

- [x] `CHANGELOG.md` is updated under `Unreleased`, and `justfile` contains `verify-jam-0002`.

## Definition of Done

- [ ] Every Acceptance Criterion above is checked.
- [x] `just verify` exits 0 (PR gate).
- [x] `just verify-ci` exits 0 once (CI parity).
- [x] Tests are written red first, then made green; the red and green stages are represented by separate commits or equivalent reviewable evidence.
- [x] Coverage thresholds in `docs/conventions/TEST_STRATEGY.md` are not regressed (see the coverage AC above for the `src-tauri/` shortfall that predates this branch).
- [x] `CHANGELOG.md` is updated under `Unreleased`.
- [ ] PR is opened using `.github/PULL_REQUEST_TEMPLATE.md`, with CI green. **PR #2 open; awaiting GitHub Actions.**
- [x] PR comments use labels from [`docs/conventions/CONVENTIONAL_COMMENTS.md`](../conventions/CONVENTIONAL_COMMENTS.md).
- [ ] At least one CODEOWNERS reviewer is requested, including `@ipc-owner` for the schema change. **Blocked: `@jametly/*` teams do not exist in the org, so `--add-reviewer` fails. Pings recorded in a PR comment instead.**
- [ ] Task `status: closed` is set after the PR merges.
- [x] No AI-authored comments restate the code.

## Escalation rules

- If missing tool or failing install → STOP, ping `@tooling-owner`.
- If changing `shared/schemas/ipc/v1.json` or its generated mirrors → STOP before implementation, ping `@ipc-owner` for sign-off.
- If adding a new dependency → STOP, ping `@tooling-owner`, and justify it in the PR body.
- If `cargo audit` reports HIGH → STOP, open a `sec:` issue, and ping `@security-owner`.
- If tests are written after the implementation → STOP; revert the sequence and redo red-then-green.
- If the task exceeds one day of work → STOP and split it into child tasks.

## Verification

```bash
just verify-jam-0002
```

This recipe expands to the focused Rust protocol tests, Python unit and event integration tests, and the Rust bridge tests. Run `just verify` and `just verify-ci` before opening the PR.
