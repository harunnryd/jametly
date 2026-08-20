# IPC contract

> Canonical source: `shared/schemas/ipc/v1.json` (committed in Phase 0). This file is the human-readable companion.

jametly's Rust host and Python sidecar communicate over **stdio JSON-RPC + NDJSON**. One JSON object per line. UTF-8 only. Newlines inside string values are escaped.

## Transport

- **Process model:** Rust spawns Python as a child process via `tauri-plugin-shell`'s `Command::new_sidecar("jametly-ai-sidecar")`. Python runs as a single subprocess for the app lifetime.
- **Wire format:** Newline-delimited JSON (NDJSON). One message per line. Lines `\r\n` or `\n` are both acceptable.
- **Framing:** line-based — no length prefix. Maximum line length 8 MB; payloads >1 MB must use the tempfile path (see below).
- **Correlation:** every request has a UUIDv4 `id`. Every reply echoes the same `id`. Fire-and-forget events have no `id` and use `null`.

## Envelope shapes

### Request (Rust → Python)

```json
{
  "id": "req-7f9c1e2a-4b3d-4e0f-8a1c-2d3e4f5a6b7c",
  "method": "chat.stream",
  "params": { "thread_id": "...", "user_text": "...", "system_prompt": "...", "provider_id": "anthropic", "model_id": "claude-sonnet-4-6", "image_path": "$APP_DATA_DIR/_blobs/abc.png" }
}
```

### Reply (Python → Rust)

```json
{ "id": "req-...", "result": { ... } }
```

or, on error:

```json
{
  "id": "req-...",
  "error": { "code": "PROVIDER_RATE_LIMIT", "message": "Anthropic 429 on claude-sonnet-4-6", "retryable": true }
}
```

### Event (Python → Rust, fire-and-forget)

```json
{
  "method": "stream.event",
  "params": {
    "correlation_id": "req-...",
    "kind": "token",
    "data": "..."
  }
}
```

## Event routing

Replies and events share one stdout stream, so the host cannot read a single line per request. `src-tauri/src/bridge.rs` reads stdout on a background task and discriminates each line via `ipc_proto::WireMessage`:

- **Reply** — matched against a pending-request map keyed by `id`; the waiting caller is woken through a oneshot channel. A reply for an unknown `id` is logged and dropped.
- **Event** — pushed onto a bounded `tokio::sync::mpsc` channel (`bridge::EVENT_CHANNEL_CAPACITY`). The consumer takes the receiver once via `Sidecar::take_events()`.
- **Request** — never expected from the sidecar; logged and dropped.

**Backpressure:** the event channel is bounded. When it is full the reader drops the *newest* event and increments a counter (`Sidecar::events_dropped()`) rather than blocking — a slow consumer must never stall reply correlation or let the reader accumulate events without limit. Events are lossy by design; anything that must not be lost belongs in a reply.

## Sidecar concurrency

The Python sidecar runs an asyncio runtime (`ai/src/jamly/bridge.py`). Each request is dispatched as its own task, so a slow handler blocks neither unrelated requests nor event delivery. Two consequences bind on the wire:

- **Replies are unordered.** A fast request answered while a slow one is in flight replies first. Correlate strictly by `id` — never by arrival position.
- **One writer.** All stdout writes serialize behind a single lock, so lines never interleave even when many tasks emit concurrently.

**Terminal signals:** exactly one of `done`, `error`, or `cancelled` is terminal per `correlation_id`; no further `stream.event` for that id follows it. Because events are lossy (see Backpressure above), a cancelled request also resolves its correlated reply as `{"id": ..., "result": {"cancelled": true}}` — the terminal outcome is never conveyed by event alone. Cancellation is normal control flow, not a failure, which is why it is a `kind` rather than an `ErrorCode`.

## Method list (Rust → Python)

| Method | Params | Result | Notes |
|---|---|---|---|
| `chat.stream` | `{thread_id, user_text, image_path?, system_prompt?, provider_id, model_id}` | `{stream_id}` (tokens arrive as `stream.event`) | Used by Ask mode |
| `chat.cancel` | `{thread_id}` | `{}` | Aborts in-flight stream |
| `transcribe.audio` | `{wav_path, language?}` | `{text}` | STT only |
| `audio.start` | `{device_id?, kind: "mic"\|"loopback"}` | `{}` | Begin capture |
| `audio.stop` | `{kind}` | `{}` | End capture |
| `capture.screenshot` | `{}` | `{png_path}` | Full primary monitor |
| `capture.region` | `{rect: {x,y,width,height}}` | `{png_path}` | Region selection |
| `meeting.start` | `{config?}` | `{meeting_id}` | Open a live meeting session |
| `meeting.stop` | `{meeting_id}` | `{}` | Close + auto-export |
| `meeting.list` | `{limit?, search?}` | `{meetings: [...]}` | History query |
| `meeting.get` | `{meeting_id}` | `{meeting: {...}}` | One meeting full transcript |
| `meeting.export` | `{meeting_id, format: "md"\|"srt"\|"vtt"\|"json"\|"pdf"}` | `{path}` | Trigger post-process export |
| `ocr.image` | `{png_path, mode: "typed"\|"handwriting"\|"auto"}` | `{markdown}` | Document → text |
| `secure.get` | `{key: "openai_api_key"\|"anthropic_api_key"\|"provider_*"}` | `{value: string \| null}` | OS keychain |
| `history.list` | `{limit?, search?}` | `{conversations: [...]}` | Chat history |
| `history.append` | `{conversation_id, role, content}` | `{message_id}` | |
| `history.search` | `{query, k?}` | `{matches: [...]}` | Uses sqlite-vec + FTS5 |
| `prompts.list` | `{}` | `{prompts: [...]}` | System-prompt library |
| `prompts.save` | `{prompt}` | `{id}` | |
| `prompts.delete` | `{id}` | `{}` | |
| `config.get` | `{key}` | `{value}` | Read config.toml |
| `config.set` | `{key, value}` | `{}` | Write |
| `providers.list` | `{kind: "ai"\|"stt"}` | `{providers: [...]}` | Built-in + custom-cURL merged |
| `providers.set_selected` | `{kind, id, variables}` | `{}` | Persists to local `config.toml` |
| `debug.stream` | `{count?}` (non-negative int, default 1) | `{count}` after `count` × `stream.event` + one `kind: "done"` | Transport diagnostic. Exercises event-before-reply ordering without any AI dependency; not a product surface. |
| `debug.sleep` | `{ms?}` (non-negative int, default 0) | `{slept_ms}`, or `{cancelled: true}` if cancelled | Transport diagnostic. Exercises concurrent dispatch and cancellation without any AI dependency; not a product surface. |

## Event list (Python → Rust)

| Event | Params |
|---|---|
| `stream.event` | `{correlation_id, kind: "token"\|"state"\|"tool_call"\|"done"\|"error"\|"cancelled", data}` |
| `audio.frame` | `{ts_ms, samples_b64, sample_rate, channels}` (diagnostic only — production path is via tempfiles) |
| `audio.level` | `{ts_ms, rms_db}` (at 10 Hz, for UI visualization) |
| `transcript.partial` | `{speaker, text, segment_id}` |
| `transcript.final` | `{speaker, text, start_ms, end_ms, confidence}` |
| `followup.emit` | `{kind: "question"\|"contradiction"\|"action"\|"todo", body, ts_ms, citations?}` |
| `qa.chunk` | `{correlation_id, text}` |
| `qa.done` | `{correlation_id, full_text, sources}` |
| `qa.interrupt` | `{proposed_action, payload, rationale}` — emitted before any tool side-effect |
| `meeting.ended` | `{meeting_id, summary_path, export_paths}` |
| `python.crash` | `{traceback, exit_code?}` |
| `python.restarted` | `{reason, pid}` |

## Binary payloads > 1 MB

PNG screenshots, captured audio chunks, OCR'd documents — anything > 1 MB crosses the IPC as a **tempfile path**, not inline bytes:

1. Rust writes to `$APP_DATA_DIR/_blobs/<uuid>.png` (or `.wav`, `.pdf`, etc.)
2. Rust sends the path in the message envelope
3. Python reads the file, processes it, deletes it after use
4. A background job cleans up files older than 1 hour

This keeps the stdio pipe unclogged and avoids base64 inflation (a 10 MB screenshot would balloon to ~13.3 MB in base64).

## Error codes (canonical)

| Code | Retryable | Meaning |
|---|---|---|
| `PARSE_ERROR` | no | JSON malformed on the wire |
| `INVALID_REQUEST` | no | Method not found, params missing/wrong type |
| `IPC_SCHEMA_VERSION` | no | Schemas don't match (Rust ↔ Python out of sync) |
| `PROVIDER_RATE_LIMIT` | yes | Upstream 429 |
| `PROVIDER_AUTH` | no | Upstream 401/403 |
| `PROVIDER_UNAVAILABLE` | yes | Upstream 5xx |
| `PYTHON_TIMEOUT` | yes | Long-running op took > `T` seconds |
| `AUDIO_DEVICE_LOST` | yes | Mic or loopback disconnected |
| `OCR_FAILED` | no | Parser could not extract content (user can re-snap) |
| `MEETING_NOT_FOUND` | no | Invalid `meeting_id` |
| `INTERNAL` | depends | Catch-all; surface `retryable` per case |

## Versioning

The IPC schema lives in `shared/schemas/ipc/v1.json`. Bumps to v2 require:

1. New schema file (`v2.json`)
2. Side-by-side v1 + v2 support for one release (deprecation window)
3. Removal of v1 in the release after that

Any breaking field addition/removal bumps the version. Adding a *new optional field* is non-breaking and does not require a version bump. See [`../decisions/0003-stdio-ipc-over-http.md`](../decisions/0003-stdio-ipc-over-http.md).

## Test strategy

Both sides test this contract:
- Rust side: `core/ipc-proto/tests/protocol_contract.rs` asserts every envelope shape matches using `insta` snapshots + property-based round-trips via `proptest`.
- Python side: `tests/integration/test_bridge_async.py` + `tests/property/test_envelope_invariants.py` (Hypothesis) assert that random NDJSON byte streams parse either to a valid `Envelope` or raise one of the typed error codes above.
- See [`../conventions/TEST_STRATEGY.md`](../conventions/TEST_STRATEGY.md).
