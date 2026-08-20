---
id: JAM-0001
title: Skeleton stdio JSON-RPC + NDJSON bridge between Rust host and Python sidecar
status: closed
type: feat
priority: P0
labels: [bridge, ipc, ai, infra]
milestone: m0-skeleton-bridge
assigned-to: unassigned
---

## Context

Phase 0 of jametly. The whole architecture (per `docs/architecture/00-overview.md`) hinges on a stdio JSON-RPC + NDJSON bridge between the Tauri/Rust host and the Python LangChain/LangGraph sidecar. Every later phase (Ask graph, STT, diarization, OCR, meeting export) is just adding methods on top of this bridge. Without a proven end-to-end roundtrip, every later integration is guesswork. See `docs/decisions/0003-stdio-ipc-over-http.md` for the rationale.

This task delivers **only** the spine: `{"method":"echo","params":{...}}` in → `{"id":"...","result":{...}}` out, plus serde/Pydantic round-trip across the wire. It does **not** deliver STT, OCR, agent graph, or any UI.

## Scope: files to touch

- `core/ipc-proto/Cargo.toml` (new) — minimal serde-only crate, no Tauri dep
- `core/ipc-proto/src/lib.rs` (new) — `Request`, `Reply`, `ReplyBody` enum, `ErrorBody`; serde derives
- `core/ipc-proto/tests/protocol_contract.rs` (new) — round-trip tests for every envelope variant (request, reply-ok, reply-err, missing-id, unknown-method, missing-params)
- `ai/pyproject.toml` (new — at repo root or `ai/`? — see decision below)
- `ai/src/jamly/__init__.py` (new)
- `ai/src/jamly/protocol.py` (new) — Pydantic mirrors of the Rust types
- `ai/src/jamly/__main__.py` (new) — stdin NDJSON loop, single `echo` method, error envelope on parse error
- `tests/__init__.py` (new)
- `tests/integration/__init__.py` (new)
- `tests/integration/test_bridge_echo.py` (new) — spawn `jamly` subprocess, write one NDJSON request, read one reply, assert shape
- `src-tauri/Cargo.toml` (new) — minimal Tauri shell, depends on `core/ipc-proto`
- `src-tauri/src/main.rs` (new) — binary entry delegating to `lib.rs`
- `src-tauri/src/lib.rs` (new) — `tauri::Builder::default().invoke_handler(generate_handler![invoke_python])`
- `src-tauri/src/bridge.rs` (new) — spawn `jamly-ai-sidecar` via `tauri-plugin-shell`, NDJSON reader/writer task with `tokio::sync::mpsc`, `#[tauri::command] async fn invoke_python`
- `Cargo.toml` (modify — root) — add `src-tauri`, `core/ipc-proto` to `members`; uncomment the placeholder deps in `[workspace.dependencies]`
- `pyproject.toml` (modify — root) — make it a uv workspace with `ai/` as member
- `justfile` (modify) — replace placeholder recipes with real ones: `py-install`, `py-test`, `rust-test`, `lint`, `verify` all wired
- `CHANGELOG.md` (modify) — add entry under [Unreleased]

## Acceptance Criteria

- [x] `cargo test -p ipc-proto` exits 0 (all serde round-trip tests pass)
- [x] `cargo test -p jametly` exits 0 (Tauri shell + bridge integration test passes — spawns Python sidecar, sends echo, asserts reply)
- [x] `uv run pytest tests/integration/test_bridge_echo.py` exits 0 (Python-side end-to-end test passes)
- [x] `just verify` exits 0
- [x] `just verify-ci` exits 0
- [x] Coverage on `core/ipc-proto` ≥ 90% line per `docs/conventions/TEST_STRATEGY.md` (100% line coverage)
- [x] Manual smoke: `echo '{"id":"r1","method":"echo","params":{"x":"hi"}}' | uv run python -m jamly` prints `{"id":"r1","result":{"x":"hi"}}`

## Definition of Done

- [x] Task file created from TEMPLATE.md
- [x] Every Acceptance Criterion above is checked
- [x] `just verify` exits 0
- [x] `just verify-ci` exits 0
- [ ] **Tests were written red first, then made green** (TDD Three Rules; historical ordering is not independently verifiable)
- [x] Coverage thresholds in `docs/conventions/TEST_STRATEGY.md` met
- [x] `CHANGELOG.md` updated under "Unreleased"
- [x] Commits on `feat/JAM-0001-stdio-bridge` use Conventional Commits (`feat(ipc):` style)
- [x] Task file's `status` set to `closed`

## Escalation rules

- If missing tool or failing install → STOP, ping `@tooling-owner`
- If need to change IPC schema → STOP, ping `@ipc-owner`
- If need to add a new dependency → STOP, ping `@tooling-owner`, justify in PR body
- If you wrote tests AFTER the implementation → you broke TDD; revert and re-do red-then-green

## Verification

```bash
just verify-jam-0001
```

This expands to: `uv run pytest tests/integration/test_bridge_echo.py -v && cargo test -p ipc-proto -- --nocapture && cargo test -p jametly -- --nocapture`.
