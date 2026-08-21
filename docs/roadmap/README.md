# jametly Roadmap

This roadmap maps task milestones to the architecture. Task files remain the source of truth for scope and acceptance criteria.

| Milestone | Tasks | Outcome |
|---|---|---|
| `m0-skeleton-bridge` | JAM-0001 | Request/reply stdio bridge and protocol contract. |
| `m1-full-duplex-ipc` | JAM-0002, JAM-0003, JAM-0025 | Events, correlation, async sidecar, cancellation, and bounded supervision. |
| `m2-capture-and-transcription` | JAM-0004, JAM-0005, JAM-0006, JAM-0027 | Audio/capture foundations, native drivers, and local configuration/security. |
| `m3-meeting-memory` | JAM-0007, JAM-0008, JAM-0009, JAM-0019, JAM-0020, JAM-0023 | Storage, VAD/STT, sessions, A/B speaker routing, audio controls, and optional provider fallbacks. Advanced diarization remains a future v0.5 task. |
| `m4-assistant` | JAM-0010, JAM-0011, JAM-0012, JAM-0024 | Provider streaming, Ask graph, summaries, follow-ups, and Q&A. |
| `m5-vision-and-history` | JAM-0013, JAM-0014, JAM-0015, JAM-0021, JAM-0026 | OCR, overlay, dashboard, searchable recall, prompts, tools, cropper, and model readiness. |
| `m6-release-readiness` | JAM-0016, JAM-0017, JAM-0022, JAM-0018 | Exports, stealth lifecycle, packaged sidecar, release artifacts, and north-star validation. |

## Phase Mapping

The repository's historical `Phase 0+` labels describe architectural maturity, while these `mN-*` milestones describe delivery waves. They are related but not interchangeable: Phase 0 is the initial bridge; `m1` completes its full-duplex transport, and later milestones consume it.
