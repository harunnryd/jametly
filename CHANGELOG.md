# Changelog

All notable changes to jametly are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Meeting session lifecycle** (`JAM-0009-meeting-session`): new `ai/src/jamly/meetings/session.py` with `meeting.start` / `meeting.stop` / `meeting.list` / `meeting.get` IPC handlers. Idempotent start rejects duplicate active sessions with `INVALID_REQUEST`. Stop flushes pending work, closes the session via a conditional `UPDATE meetings SET ended_at = CURRENT_TIMESTAMP WHERE id = ? AND ended_at IS NULL`, and emits `meeting.ended` exactly once (the rowcount gate is the linearization point). List/get return stable bounded results with FTS5 search. Cold-start recovery writes a `checkpoints(thread_id=meeting_id)` row with `status="recovered_on_cold_start"` for every meeting whose `ended_at IS NULL` and does not close them; the user/dashboard decides the recovery UX. No new dependencies, no schema migration, no IPC schema change.
- **Local STT pipeline** (`JAM-0008-stt-pipeline`): Python-owned speech-to-text pipeline with a lazy `faster-whisper` CTranslate2 adapter, a ring-buffered silero-VAD gate that turns a 30 ms ingest cadence into the exact 512-sample frames silero accepts, cumulative partials plus one final event per voiced segment, deterministic offline-friendly tests against a fake provider, and typed-error mapping for bad inputs, unavailable models, and slow inference. Remote speech-to-text providers remain approval-gated in JAM-0020 and speaker diarization in JAM-0019.
- **SQLite meeting store** (`JAM-0007-sqlite-store`): Python-owned standard-library SQLite schema with versioned migrations, meetings/utterances/messages/action items, FTS5 search, bounded results, transaction rollback, and no telemetry tables. Vector search and the Rust read-cache remain approval-gated in JAM-0031/JAM-0032.
- **Secure config contract** (`JAM-0006-secure-config`): Rust-owned provider-secret namespace, non-disclosing typed errors, deterministic in-memory secret store, and strict Python configuration defaults under `~/.config/jametly/`. Native OS keychains and atomic TOML persistence remain approval-gated in JAM-0029 and JAM-0030.
- **Screen capture abstraction** (`JAM-0005-screen-capture`): standalone Rust capture contract with overflow-safe region validation, deterministic RGBA mock capture, sanitized permission/unavailable errors, confined PNG blob output, and stale-blob cleanup. Native xcap monitor capture remains approval-gated in JAM-0028.
- **Audio backend abstraction** (`JAM-0004-audio-backend`): standalone Rust audio contract with 16 kHz mono PCM frames, monotonic timestamps, bounded drop-newest frame delivery, deterministic mock capture, lifecycle/device-loss errors, and chunking property tests. Native microphone/loopback drivers remain approval-gated in JAM-0027.
- **Async sidecar runtime** (`JAM-0003-async-sidecar-runtime`): new `ai/src/jamly/bridge.py` running an asyncio runtime — one task per request, so a slow handler blocks neither unrelated requests nor event delivery. Adds `OutboundStream` (single lock-serialized stdout writer, no interleaved NDJSON), `TaskRegistry` (in-flight tasks keyed by request `id`, with a `thread_id` index for the future `chat.cancel`), a new `stream.event` kind `cancelled`, and the `debug.sleep` transport diagnostic. Cancellation resolves both the terminal event and the correlated reply, since events are lossy by design. Stdin is read off the event loop so a blocking pipe read cannot stall in-flight handlers. `__main__.py`'s synchronous `REGISTRY`/`_handle`/`_serve` remain for wire compatibility.
- **Full-duplex IPC spine** (`JAM-0002-ipc-events`): additive `Event` envelope in `shared/schemas/ipc/v1.json` with serde (`ipc_proto::{Event, WireMessage}`) and Pydantic (`jamly.protocol.Event`) mirrors; the Rust bridge now reads sidecar stdout on a background task, correlates replies by id, and surfaces fire-and-forget events through a bounded channel (`EVENT_CHANNEL_CAPACITY = 256`, drop-newest overflow policy with a dropped-event counter). Python gains a method registry and the `debug.stream` transport diagnostic; `Reply` rejects envelopes carrying both `result` and `error`. Contract tests add an `insta` envelope snapshot and `proptest` invariants.
- **Phase 0 skeleton bridge** (`JAM-0001-stdio-bridge`): `core/ipc-proto` (serde envelope types), `ai/src/jamly` (Python sidecar with `echo` + error envelopes), `src-tauri` (Tauri shell + `bridge::Sidecar` via `tokio::process::Command`). Rust bridge/protocol tests, Python unit tests, and subprocess integration tests pass with 100% `ipc-proto` line coverage and 91.89% Python coverage. Verified manually: echo, unknown-method, malformed-JSON paths all produce canonical wire output.
- **GOAL.md** — mission + 5 architectural lines (immutable) + non-goals + 2-part north-star test (invisibility + recall). Source of truth for the architectural commitments.
- Day-0 repo scaffold: meta files (LICENSE, README, AGENTS, CONTRIBUTING, STYLE, SECURITY, TRADEMARKS, CHANGELOG, GOAL), .claude/ ops config (settings + commands + hooks), docs/ (architecture + decisions + tasks + **conventions**), justfile (tiered `verify` / `verify-ci` / `verify-strict` / `verify-full`), CODEOWNERS, .pre-commit-config.yaml (ruff + guard + `dcg` + comment-density), .github/ (PR + issue templates + CI), workspace manifests (package.json, pnpm-workspace.yaml, Cargo.toml, pyproject.toml, tauri.conf.json)
- **docs/conventions/TEST_STRATEGY.md**: per-substack test layer-mix, tooling picks, coverage thresholds, mutation testing schedule, AI/LLM eval tooling (DeepEval + LangSmith), 2-tier confidence model
- **docs/conventions/CONVENTIONAL_COMMENTS.md**: PR-review label convention (12 labels × 3 decorations × 7 domain tags)
- `docs/decisions/0001..0006`: 6 MADR-format ADRs (Tauri over Electron, Python AI sidecar, stdio IPC, MIT + trademark, OSS no Pro tier, macOS stealth honest disclosure)
- `docs/architecture/{00-overview,01-ipc,02-modules}`: single ASCII diagram + full IPC method list + module map

### Changed
- README.md: "no cloud calls" wording reconciled with SECURITY.md "model downloads OK" (model downloads are user-key configured, link to SECURITY §Privacy posture).
- `docs/decisions/0006-macos-stealth-honest-disclosure.md` + SECURITY.md: stealth tiers renamed from "Tier 0/1/2" → "Band A/B/C" to eliminate word collision with the verify ladder (`verify`/`verify-ci`/`verify-strict`/`verify-full`).
- `tauri.conf.json`: `minimumSystemVersion` 10.15 → 13.0 to match the bug-report envelope.
- `docs/architecture/01-ipc.md`: sidecar binary `pluely-ai-sidecar` → `jametly-ai-sidecar`.
- AGENTS.md, CONTRIBUTING.md, STYLE.md: minor trim, link to canonical sources instead of duplicating tables.

### Removed
- `docs/decisions/0001..0006.md`: scrubbed stale references to a non-existent ADR-0007.
- `docs/decisions/0001..0006.md`: scrubbed "Pluely" mentions → "predecessor codebase".
- CHANGELOG.md: removed stale "Pre-day-0 scaffolding" + "Migration from jametly-v1" sections (v1 is gone; this dir is the rebuild).

### Fixed
- SECURITY.md: dropped dangling `docs/decisions/0007-security-contact.md` forward reference.
- `.claude/settings.json`: tightened dangerous allow-list (`format *` anchored, dead `.drop*` removed, `launchctl*`/`systemctl*` moved to `deny`, `chmod 777` + `gh repo {delete,edit}*` denied).

### Security
- See SECURITY.md for the privacy posture and macOS stealth disclosure.
