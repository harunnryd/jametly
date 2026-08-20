# Sub-agents

This directory contains sub-agent definitions for Claude Code (and compatible agents).

## When to add one

Add a sub-agent when a domain repeats across many tasks and the agent's context keeps drifting. Good candidates for jametly:

- `audio-expert.md` — owns cross-platform audio capture, ringbuffer semantics, per-OS quirks
- `ipc-owner.md` — guards the IPC contract schema; reviews any change touching `shared/schemas/ipc/v1.json`
- `rust-owner.md` — Tauri + reusable core crates; windows, NSPanel, stealth
- `python-owner.md` — LangChain/LangGraph agents, STT/diar/OCR pipeline
- `frontend-owner.md` — React UI, streaming markdown, provider cards, onboarding orchestrator
- `test-owner.md` — owns the 4-tier verify ladder, mutation suites, the `tests/` directory

## Format

Each file is markdown with YAML frontmatter:

```markdown
---
name: <id>
description: <one-sentence when-to-delegate hint>
model: <model-id>
tools: [<tool>, ...]
---

<one-paragraph scope of authority>

<numbered rules of engagement>

<escalation policy>
```

The `description` field is how the parent agent decides whether to delegate. Make it specific and trigger-rich.

## Adding one

1. Create the file in this directory
2. Test: the parent should auto-discover it on next session
3. Update `CODEOWNERS` so changes to the file route to `@tooling-owner`
