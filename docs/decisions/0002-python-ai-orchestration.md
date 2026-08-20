---
status: accepted
date: 2026-08-20
---

# 0002 — Python owns the AI sidecar; LangChain + LangGraph

## Context and problem statement

The AI layer needs: streaming chat from 10+ LLM providers (OpenAI, Anthropic, Gemini, Mistral, Cohere, Groq, Perplexity, OpenRouter, Ollama, custom cURL), real-time speaker-diarized meeting transcription, on-demand vision, document OCR, smart follow-up suggestions, and tool-calling with human approval. This is the largest piece of jametly. Where does it live?

## Decision drivers

- LangChain / LangGraph are the most mature Python agent frameworks in 2026 (incl. `init_chat_model`, `create_agent`, `SqliteSaver`, `SqliteStore`, full SSE streaming, `interrupt_before` gates).
- `faster-whisper`, `silero-vad`, `diart`, `marker-pdf`, `sentence-transformers`, `sqlite-vec` are all native Python wheel ecosystems — matching Rust re-implementations don't exist or lag.
- Most ML team familiarity is Python, not Rust.
- Test surface for graph state is well-trodden (pytest + LangGraph checkpointer tests).
- Live-meeting graph needs an event loop + state management with sub-200ms cancellation propagation — Python's `asyncio` + LangGraph's `Command(goto=…)` + `Send`-based fan-out are a clean fit.

## Considered options

**A. Python sidecar.** Spawn `python3 -m jamly` from Rust. All AI logic lives in Python. IPC over stdio NDJSON. Rust stays thin (window, audio capture, capture, IPC bridge).

**B. JS-side AI via Vercel AI SDK or LangChain.js.** Same renderer that draws the UI also runs AI orchestration. No sidecar. Weaker graph-state semantics, fewer mature diarization/STT/OCR libs for Node, no PyO3-style wins.

**C. Rust-side AI via `rig` or hand-rolled graph.** Single language; no IPC. Missing the entire ecosystem of mature Python ML libs. Lose OCR (Rust `marker-pdf` is thin), diarization (`diart` is Python-only), LangGraph semantics (Rust `langgraph-rs` lags months behind).

## Decision outcome

Chosen option: **A — Python sidecar with LangChain + LangGraph**.

Python becomes the AI orchestration runtime. Rust stays thin: process spawn, stdio framing, window/shortcut/capture, audio frame forwarding. The IPC contract lives in `shared/schemas/ipc/v1.json` and is the seam.

### Consequences

- **Good:** full ecosystem of mature ML libs in one place.
- **Good:** LangGraph's `SqliteSaver` + `SqliteStore` give us checkpointed graph state + cross-meeting memory for free.
- **Good:** agents-as-tools + `interrupt_before` gates fit the "ask user before screen-capture" UX cleanly.
- **Bad:** cold-start 0.6–1.0 s for the Python process. Mitigated by spawning in parallel with WebView load + warm-importing LangChain. Phase 5 will ship `pyoxidizer`-built single-binary distribution to keep both dev workflow fast and installer small.
- **Bad:** GIL-driven GC pauses can starve audio consumers if Python is busy. Bounded mpsc + ringbuffer in Rust + overflow-drop policy mitigates this.

## References

- LangChain Python: https://docs.langchain.com
- LangGraph streaming + interrupt: https://langchain-ai.github.io/langgraph/concepts/interrupts/
- `faster-whisper`: https://github.com/SYSTRAN/faster-whisper
- `diart`: https://github.com/juanmc2005/diart
- `marker-pdf`: https://github.com/datalab-to/marker
- `pyannote.audio`: https://github.com/pyannote/pyannote-audio
