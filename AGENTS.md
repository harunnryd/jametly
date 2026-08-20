# jametly — instructions for AI coding agents

> Read this file first. Then read `docs/conventions/TEST_STRATEGY.md` and `docs/architecture/00-overview.md`. Stop.

If you are Claude Code: this content is mirrored by `.claude/CLAUDE.md`. For all other agents, this file is canonical.

> For human contributors (PR etiquette, code of conduct, RFC process), read [`CONTRIBUTING.md`](./CONTRIBUTING.md) instead.

## Build & verify (the only commands you need)

```bash
just install          # one-time: pull deps for all three stacks
just verify           # fast PR gate (≤ 3 min): lint + unit + smoke
just verify-ci        # CI gate (≤ 12 min): + coverage + e2e
just verify-strict    # nightly: + mutation + hypothesis + perf budgets
just verify-full      # release: + extended e2e + parallel
```

See [`justfile`](./justfile) and [`docs/conventions/TEST_STRATEGY.md`](./docs/conventions/TEST_STRATEGY.md) for the full tier breakdown. Per-tier gates live in `justfile`; this ladder appears in exactly one other place (`.claude/CLAUDE.md`) — do not duplicate.

## Stack

- **Desktop shell:** Tauri 2 (Rust) + React 19 + Vite 5 + Tailwind v4 + Radix UI
- **AI sidecar:** Python 3.12+ via `uv`, LangChain + LangGraph
- **Database:** SQLite (Python owns writes, Rust read-cache via `tauri-plugin-sql`)
- **IPC:** stdio JSON-RPC + NDJSON between Rust host and Python sidecar
- **Audio:** per-OS native loopback (cpal / cidre / wasapi / libpulse) + `faster-whisper`
- **Diarization:** `diart` (live) + `pyannote/speaker-diarization-community-1` (post-process)
- **OCR:** `marker-pdf` (primary) + local VLM fallback via Ollama
- **Vector search:** `sqlite-vec` + `sentence-transformers all-MiniLM-L6-v2`
- **Tests:** `pytest` + `cargo test` + `tauri-driver`

## Build & verify (the only commands you need)

```bash
just install          # one-time: pull deps for all three stacks
just verify           # fast PR gate (≤ 3 min): lint + unit + smoke
just verify-ci        # CI gate (≤ 12 min): + coverage + e2e
just verify-strict    # nightly: + mutation + hypothesis + perf budgets
just verify-full      # release: + extended e2e + parallel
```

See [`justfile`](./justfile) and [`docs/conventions/TEST_STRATEGY.md`](./docs/conventions/TEST_STRATEGY.md) for the full tier breakdown.

## Where things live

| Path | Owns |
|---|---|
| `src-tauri/` | Tauri 2 shell + Rust commands |
| `core/` | Standalone Rust crates (testable in isolation) |
| `ai/` | Python sidecar (uv-managed) |
| `app/` | React 19 + Vite 5 frontend |
| `shared/schemas/ipc/v1.json` | Canonical IPC contract |
| `docs/architecture/` | System diagrams, IPC protocol, module map |
| `docs/decisions/` | MADR-format ADRs (0001..NNNN) |
| `docs/conventions/` | TEST_STRATEGY, CONVENTIONAL_COMMENTS |
| `docs/tasks/JAM-XXXX.md` | Per-task files (Context / Scope / AC / DoD) |
| `tests/` | Cross-stack e2e, cassettes, snapshots, perf |

## Hard rules

1. **IPC contract** lives in `shared/schemas/ipc/v1.json`. Never edit without pinging `@ipc-owner`. (See [CODEOWNERS](./CODEOWNERS).)
2. **Never bump major dependency versions** without pinging `@tooling-owner`.
3. **Never merge your own PR** — open it and stop.
4. **Every PR must link a task file** in `docs/tasks/`.
5. **Never commit secrets.** `.env` is git-ignored; `.env.example` lists keys only.
6. **Comments explain "why", never "what".** Code that needs comments is code that needs refactoring.
7. **TDD's Three Rules** (Martin/Beck) on every new public command/API. See `docs/conventions/TEST_STRATEGY.md`.
8. **PR-review comments use Conventional Comments labels** — `nitpick:`, `suggestion:`, `issue:`, etc. See `docs/conventions/CONVENTIONAL_COMMENTS.md`.

## Picking up a task

1. Read `docs/tasks/<id>.md` in full. Confirm `status: ready`.
2. Run `just verify` on a clean tree to confirm baseline green.
3. **Write the test first** (red). Run it — confirm it fails for the reason the AC requires.
4. Write the minimum code to pass it (green). Refactor if obvious.
5. Run `just verify` again. Must exit 0.
6. Open a PR using `.github/PULL_REQUEST_TEMPLATE.md`. Body: `Closes JAM-XXXX` + paste `just verify` output + the risk checklist.
7. STOP. Do not merge.
8. Mark the task `status: closed` once the PR merges.

The `.claude/commands/task.md` slash command automates this flow.

## Escalation rules

| Situation | Action |
|---|---|
| Missing tool / failing install | STOP, ping `@tooling-owner` |
| Need to change IPC schema | STOP, ping `@ipc-owner` |
| Need to add a new dependency | STOP, ping `@tooling-owner`, justify in PR body |
| Test passes locally, fails in CI | Re-read CI log once; if stuck, ping `@tooling-owner` |
| `cargo audit` reports HIGH | STOP, open `sec:` issue, ping `@security-owner` |
| Test is flaky (<5% fail rate) | Quarantine with `@pytest.mark.flaky`, file follow-up task |
| Task exceeds 1 day of work | STOP, split into subtasks, do not exceed scope |
| AI-authored inline comment restates code | DELETE before commit (`STYLE.md` "AI-authored comments") |

## Anti-patterns (do NOT do these)

- **Comments explaining what the code already says.** Apply Kent Beck's test: *add a comment you wish you had when reading the code / remove a comment that just says what the code says*. If a comment fails test 2 and you cannot justify it under `STYLE.md` "Must always", delete it and refactor. AI-generated inline comments restating the next line are a CI smell — strip them before commit.
- TODOs without owner + ticket: `# TODO(@alice, JAM-0100): ...`
- Catch-all errors that swallow exceptions
- Tests that test the test, not the code (assertion-free tests, mock-everything tests)
- Adding a dep without justification in the PR description
- Reading the whole codebase before acting — read the task file + the relevant dir + the relevant IPC schema
- Claiming a task done without running `just verify`
- E2E tests that assert CSS classes (test the framework, not your code)
- Mock-heavy LangGraph tests that assert on `llm.invoke` arguments (the mock is the system under test — guarantees nothing)

## Boundaries (what you decide alone vs what needs approval)

| Decision | Agent decides alone | Must ask |
|---|---|---|
| Branch name (`feat/JAM-XXXX-slug`) | yes | — |
| Commit subject (Conventional Commits) | yes | — |
| Internal refactor | yes | — |
| Public API change | — | yes, owner of affected dir |
| New dependency | — | yes, `@tooling-owner` |
| IPC schema change | — | yes, `@ipc-owner` |
| Force-push / history rewrite | — | never |
| Merge own PR | — | never |
| Release | — | never (`@release-owner` only) |
