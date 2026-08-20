---
status: accepted
date: 2026-08-20
---

# 0003 — stdio JSON-RPC + NDJSON over local HTTP / Unix socket

## Context and problem statement

The Rust host and the Python sidecar must talk. Options for the wire: stdio JSON-RPC, localhost HTTP+SSE, Unix domain socket, gRPC, embedded Python via PyO3. Which?

## Decision drivers

- One process model: one Python sidecar per app session; restart on crash; health-check via heartbeat.
- Streaming: token-by-token from LLM; PCM frames from audio; meeting events; mode-switch pings. Need backpressure.
- Binary payloads: PNG screenshots and WAV audio chunks can be ~50 KB–10 MB.
- Dev ergonomics: easy to attach `cat | jq` for debugging; visible process tree; one place for both stdout (events) and stderr (logs).
- Distribution: bundled binary needs to "just work" on first run, no port conflicts, no firewall prompts.
- We've already proven this pattern in `reality/` (per project memory) — same shape, fewer footguns.

## Considered options

**A. stdio JSON-RPC + NDJSON.** One line per message. Fire-and-forget events + request/reply both go through the same channel. Bounded mpsc backpressure naturally.

**B. Localhost HTTP + SSE.** Python runs a small FastAPI server; Rust uses `reqwest`. Familiar to web devs but needs port allocation and CORS sanity.

**C. Unix domain socket / Windows named pipe.** Native binary lane; great for binary frames. OS-specific lifecycle complexity.

**D. gRPC / Connect-RPC.** Streaming + type-safe + code-gen. Heavy for our payload volume; codegen complexity.

**E. PyO3 — embed Python in Rust.** No IPC at all. Trade latency for binary bloat + Python version lock.

## Decision outcome

Chosen option: **A — stdio JSON-RPC + NDJSON**, with tempfile path for payloads >1 MB.

Rationale:
- Same shape proven in `reality/` (per project memory).
- Streaming token flow (≤ 100 msg/s from LLM, ≤ 33 msg/s from audio) fits well within stdio's line-buffered pipe.
- Backpressure: pipe blocks naturally; we use bounded mpsc internally to never let the audio capture loop stall.
- Dev: `cat | jq` on the pipe is the debugger.
- Fire-and-forget events + request/reply share one channel — no second transport to maintain.

Binary screenshots and WAV chunks are written to `$APP_DATA_DIR/_blobs/<uuid>.{ext}` and only the path crosses the JSON envelope. A background cleanup job removes files older than 1 hour.

### Consequences

- **Good:** zero port allocation, zero firewall prompts, zero CORS.
- **Good:** one channel to debug; one parser to maintain.
- **Good:** works identically during dev (`uv run`) and in production (PyOxidizer binary, Phase 5).
- **Bad:** line-based framing caps line length at 8 MB; large payloads must use tempfile path. Acceptable tradeoff.
- **Bad:** stdio from a Windows process needs careful handle inheritance; mitigated by using `tauri-plugin-shell` which handles the wrapping.

## References

- Tauri sidecar pattern: https://v2.tauri.app/develop/sidecar/
- NDJSON spec: https://ndjson.org/
- `reality/` reference: project memory `project_reality_app.md` (prior Tauri+Python sidecar in same monorepo)
