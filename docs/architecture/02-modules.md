# Modules

> One line per directory. New modules land here when added; old modules stay here for context. Mirrors the actual filesystem layout that `docs/decisions/0001..0006` locked in.

## Top-level

| Path | Owns |
|---|---|
| `src-tauri/` | Tauri 2 shell + Rust commands + plugin wiring |
| `core/` | Standalone Rust crates (reusable, testable without Tauri runtime) |
| `ai/` | Python sidecar (uv-managed) |
| `app/` | React 19 + Vite 5 frontend |
| `shared/` | Cross-language contracts (IPC schema at `shared/schemas/ipc/v1.json`) |
| `docs/` | Architecture + decisions + tasks + conventions |
| `tests/` | Cross-stack e2e, cassettes, snapshots, perf benchmarks |
| `justfile` | Single ergonomic command surface |
| `.claude/` | AI agent ops config |
| `.github/` | PR templates, CI workflows, issue templates |

## `src-tauri/` (Phase 0+)

| Path | Owns |
|---|---|
| `src-tauri/src/main.rs` | Binary entry |
| `src-tauri/src/lib.rs` | Tauri builder + plugin registration |
| `src-tauri/src/bridge.rs` | Python sidecar lifecycle + stdio NDJSON framing |
| `src-tauri/src/window.rs` | Main + dashboard + cropper webview windows, NSPanel styling |
| `src-tauri/src/shortcuts.rs` | Global hotkeys + window move nudge |
| `src-tauri/src/audio/` | Thin re-export of `core/audio-backend` |
| `src-tauri/src/capture.rs` | Screen capture + per-monitor overlay selection |
| `src-tauri/src/db/` | SQLite read-cache (writes happen Python-side) |
| `src-tauri/src/license/` | *not present in v2; deliberately removed* |
| `src-tauri/capabilities/` | Tauri permission JSON |
| `src-tauri/tauri.conf.json` | Bundle config + window settings |

## `core/` (Phase 0+)

| Path | Owns |
|---|---|
| `core/audio-backend/` | cpal + cidre + wasapi + libpulse; no Tauri dep; `#[automock]` trait for per-OS backends |
| `core/screen-capture/` | xcap wrapper, no Tauri dep |
| `core/sqlite-store/` | rusqlite + migrations, no Tauri dep |
| `core/ipc-proto/` | serde structs mirroring `shared/schemas/ipc/v1.json`; contract tests via `insta` + `proptest` |
| `core/secure-store/` | OS keychain wrapper (user API keys only — no license, no machine-uid) |
| `core/stealth-macos/` | objc2 NSWindow SPI + CGEventTap, optional opt-in tier |

## `ai/` (Phase 0+)

| Path | Owns |
|---|---|
| `ai/src/jamly/__main__.py` | Sidecar entry — reads stdin NDJSON, writes stdout NDJSON |
| `ai/src/jamly/protocol.py` | Pydantic mirrors of `shared/schemas/ipc/v1.json` |
| `ai/src/jamly/bridge.py` | asyncio reader/writer coroutines + cancellation |
| `ai/src/jamly/audio.py` | PCM ingest + `silero-vad` orchestration |
| `ai/src/jamly/capture.py` | Image ingest → multimodal LangChain message |
| `ai/src/jamly/ocr.py` | `marker-pdf` primary + `qwen2.5-vl:7b` Ollama fallback |
| `ai/src/jamly/llm/__init__.py` | `build_chat_model()` factory (wraps `init_chat_model`) |
| `ai/src/jamly/llm/curl_model.py` | `CurlChatModel(BaseChatModel)` — user-paste cURL providers |
| `ai/src/jamly/stt/base.py` | `STTProvider` ABC + event-emitter partial/final semantics |
| `ai/src/jamly/stt/faster_whisper.py` | Local CTranslate2 Whisper |
| `ai/src/jamly/stt/openai_whisper.py` | OpenAI Realtime WS → REST priority chain |
| `ai/src/jamly/stt/groq_whisper.py` | Groq REST (high-throughput fallback) |
| `ai/src/jamly/stt/custom.py` | User-paste cURL STT providers |
| `ai/src/jamly/diar/__init__.py` | `DiartLive` + `PyannotePostProcess`; speaker name binding |
| `ai/src/jamly/agent/__init__.py` | Ask graph, meeting graph, follow-up sub, Q&A sub |
| `ai/src/jamly/agent/tools.py` | `@tool` defs: `screenshot`, `take_clipboard`, `search_history`, `switch_provider`, `run_stt` |
| `ai/src/jamly/agent/checkpoint.py` | `SqliteSaver` factory + thread_id utils |
| `ai/src/jamly/db.py` | Local SQLite store + FTS5 search |
| `ai/src/jamly/llm/__init__.py` | `ProviderRegistry`, `build_chat_model`, `ProviderInfo`, `ChatMessage`, `ChatModel` protocol |
| `ai/src/jamly/llm/base.py` | Built-in `ollama` / `faster-whisper` providers, provider-info pydantic, chat-model ABC |
| `ai/src/jamly/llm/fake.py` | `FakeChatModel` (deterministic tokens + delay + optional mid-stream failure) for tests |
| `ai/src/jamly/agent/__init__.py` | Package marker |
| `ai/src/jamly/agent/chat.py` | `chat.stream` / `chat.cancel` / `providers.list` / `providers.set_selected` handlers, canonical error mapping, `PYTHON_TIMEOUT` via `asyncio.wait_for` |
| `ai/src/jamly/meetings/__init__.py` | Package marker |
| `ai/src/jamly/meetings/session.py` | Meeting session lifecycle, `meeting.*` IPC handlers, cold-start recovery |
| `ai/src/jamly/meetings/summarizer.py` | LCEL + `with_structured_output(MeetingSummary)` |
| `ai/src/jamly/meetings/extractor.py` | `with_structured_output(ActionItems)` with `source_utterance_ids` |
| `ai/src/jamly/meetings/exporters/` | `pysrt`, `webvtt-py`, `weasyprint`, `pydantic.md/json` |
| `ai/src/jamly/meetings/index.py` | sqlite-vec + FTS5 hybrid search |
| `ai/src/jamly/config.py` | pydantic-settings, `$APP_DATA_DIR/config.toml` |
| `ai/pyproject.toml` | uv-managed Python package |

## `app/` (Phase 2+)

| Path | Owns |
|---|---|
| `app/src/pages/` | Route-level views keyed by `?window=` (`overlay`, `dashboard`, `cropper`, etc.) |
| `app/src/components/{ui,...}/` | shadcn primitives + custom widgets |
| `app/src/hooks/` | `useChatCompletion`, `useCompletion`, `useSystemAudio`, etc. |
| `app/src/lib/bridge.ts` | Typed wrapper around `@tauri-apps/api/core::invoke` |
| `app/src/lib/streamingMarkdown.ts` | Marked-at-stream + react-markdown-at-finalize (from natively research) |
| `app/index.html` | Single entry → `?window=` dispatch |

## `shared/`

| Path | Owns |
|---|---|
| `shared/schemas/ipc/v1.json` | Canonical IPC contract (single source of truth) |
| `shared/README.md` | Cross-language contract notes |

## `tests/` (cross-stack, Phase 0+)

```
tests/
├── README.md                  # naming conventions, marker table
├── conftest.py                # shared pytest fixtures (added when integration fixtures land)
├── unit/                      # fast python unit tests (fakes for LLM)
├── property/                  # Hypothesis invariants (IPC envelope, STT bounds)
├── snapshot/                  # syrupy fixtures (prompts, transcript exports)
├── cassettes/                 # pytest-recording VCR (OpenAI, Anthropic, Whisper)
├── integration/               # python sidecar + mocked bridge
├── e2e/                       # WebdriverIO + @wdio/tauri-service (overlay flows)
├── perf/                      # pytest-benchmark (audio pipeline budgets)
├── stealth/                   # gated on JAMETLY_STEALTH_E2E=1
├── golden/                    # insta-style cross-stack snapshots
└── cassettes/.gitkeep
```

`src-tauri/src/**/tests/`, `core/*/tests/`, `app/src/__tests__/`, `shared/schemas/__tests__/` mirror the actual layout. See [`../conventions/TEST_STRATEGY.md`](../conventions/TEST_STRATEGY.md).

## `docs/`

| Path | Owns |
|---|---|
| `docs/architecture/` | 00-overview (this file), 01-ipc, 02-modules |
| `docs/decisions/` | MADR-format ADRs (0001..NNNN) |
| `docs/conventions/` | `TEST_STRATEGY.md`, `CONVENTIONAL_COMMENTS.md` |
| `docs/tasks/` | Per-task files `JAM-XXXX-slug.md` + `TEMPLATE.md` + `README.md` |
