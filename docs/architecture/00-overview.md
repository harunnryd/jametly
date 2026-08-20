# Architecture overview

> One ASCII diagram + one paragraph per box. Single source of truth for "what talks to what". Refined in v2 against 12+ research agents (Pluely v0 + natively-cluely-ai-assistant + LangChain / LangGraph / pyannote / faster-whisper / marker-pdf library picks).

```
       ┌─────────────────────────────────────────────────────────────────────────────┐
       │                              user's machine                                  │
       │                                                                               │
       │      ┌────────────────┐         ┌──────────────────┐         ┌────────────┐  │
       │      │  meeting app   │ audio   │   jametly shell  │ stream  │  local LLM │  │
       │      │  (Zoom, Meet,  │ ───────►│  (Tauri + Rust)  │ ───────►│  (Ollama   │  │
       │      │   browser tab) │ out     │                   │  NDJSON  │   or fast   │  │
       │      └────────────────┘         │  ┌──────────────┐ │   over  │   model)    │  │
       │                                 │  │  Python      │ │  stdio  │             │  │
       │                                 │  │  sidecar     │ ├────────►│  STT:       │  │
       │                                 │  │  (uv +       │ │         │  faster-    │  │
       │                                 │  │  LangGraph)  │ │         │  whisper    │  │
       │                                 │  └──────────────┘ │         │             │  │
       │                                 │                   │         │  VAD:       │  │
       │                                 │  ┌──────────────┐ │         │  silero-    │  │
       │                                 │  │ 600×54       │ │         │  vad        │  │
       │                                 │  │ NSPanel      │ │         │             │  │
       │                                 │  │ overlay      │ │         │  Diar:      │  │
       │                                 │  │ (React 19)   │ │         │  diart +    │  │
       │                                 │  └──────────────┘ │         │  pyannote   │  │
       │                                 └──────────────────┘         │             │  │
       │                                                                 │  OCR:       │  │
       │                                                                 │  marker-pdf │  │
       │                                                                 │  + VLM      │  │
       │                                                                 └────────────┘  │
       └─────────────────────────────────────────────────────────────────────────────┘
                                          ▲
                                          │ user input + display
                                          │
                                       user
```

## Boxes

| Box | Path | Owns |
|---|---|---|
| **Meeting app** (Zoom, Meet, browser tab, Slack huddle) | n/a | Source of audio jametly listens to. No per-app integration; OS-level loopback capture only. |
| **jametly shell (Tauri + Rust)** | `src-tauri/`, `core/` | Window lifecycle, global shortcuts, screen capture, audio capture (cpal/cidre/wasapi/libpulse), SQLite read-cache, IPC bridge to Python. |
| **Python sidecar (uv-managed)** | `ai/` | AI orchestration (LangChain + LangGraph), STT (`faster-whisper`), VAD (`silero-vad`), diarization (`diart` live + `pyannote/speaker-diarization-community-1` post-process), OCR (`marker-pdf`), meeting graph, SQLite writes via SQLAlchemy 2.0, semantic search via `sqlite-vec`. |
| **Overlay (React 19 + Vite 5)** | `app/` | 600×54 floating bar, multi-surface (`?window=` query). |
| **Local LLM / STT / VAD / OCR / retrieval** | various | `qwen2.5:7b-instruct` via Ollama, `faster-whisper`, `silero-vad`, `diart`, `marker-pdf`, `qwen2.5-vl:7b` for handwriting, `sqlite-vec` + `all-MiniLM-L6-v2`, `SqliteStore` + `fastembed:BAAI/bge-small-en-v1.5`. |

## Data flow summary

1. **Capture.** Rust core reads system audio at native sample rate, resamples to 16 kHz mono, writes PCM frames into a bounded `tokio::mpsc`.
2. **Ingest.** Python sidecar pops frames, runs VAD, and on voiced segments runs speaker-diarization + STT (live phase) or schedules a post-process diarization (offline batch, better accuracy).
3. **Accumulate.** Transcribed utterances accumulate in a bounded `deque[Utterance](maxlen=20)` plus the running meeting transcript in SQLite.
4. **Generate.** LangGraph agents (Ask / follow-up / Q&A) read the accumulator + rolling window and produce streamed tokens.
5. **Render.** Tokens flow back through stdio NDJSON → Rust → Tauri `chat_stream_chunk` event → React renders into the overlay.
6. **Persist.** Final utterances and assistant messages written to SQLite via SQLAlchemy 2.0. Auto-export MD / SRT / VTT / JSON on meeting end (PDF via WeasyPrint when post-process phase is live). LangGraph `SqliteSaver` checkpointed per `thread_id == meeting_id`.

## Cross-language truth

`shared/schemas/ipc/v1.json` is the canonical IPC contract. Both `core/ipc-proto/` (serde structs) and `ai/src/jamly/protocol.py` (Pydantic models) are generated from / kept in sync with it. Either side can break a PR; the PR template's risk checklist catches explicit schema changes.

## See also

- [`01-ipc.md`](./01-ipc.md) — full IPC method + event list
- [`02-modules.md`](./02-modules.md) — per-module one-line purpose
- [`../decisions/0001-tauri-over-electron.md`](../decisions/0001-tauri-over-electron.md)
- [`../decisions/0002-python-ai-orchestration.md`](../decisions/0002-python-ai-orchestration.md)
- [`../decisions/0003-stdio-ipc-over-http.md`](../decisions/0003-stdio-ipc-over-http.md)
- [`../conventions/TEST_STRATEGY.md`](../conventions/TEST_STRATEGY.md) — per-substack test layer-mix
