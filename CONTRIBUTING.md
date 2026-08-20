# Contributing to jametly

> AI agents: read `AGENTS.md` first. This file is the human-facing etiquette. Tests: see [`docs/conventions/TEST_STRATEGY.md`](./docs/conventions/TEST_STRATEGY.md). Comment policy: see [`STYLE.md`](./STYLE.md). PR-review labels: see [`docs/conventions/CONVENTIONAL_COMMENTS.md`](./docs/conventions/CONVENTIONAL_COMMENTS.md).

## TL;DR

1. Pick or open a task file in `docs/tasks/JAM-XXXX-slug.md`.
2. Create a branch: `feat/JAM-0042-vad-gate` (or `fix/`, `chore/`, `refactor/`, `docs/`, `test/`).
3. **Write the failing test first** (red). Run it. Confirm it fails for the right reason.
4. Implement the minimum code to pass it (green).
5. Refactor if obvious. No tests should break.
6. Run `just verify` until it exits 0. Run `just verify-ci` once for parity with CI.
7. Open a PR using `.github/PULL_REQUEST_TEMPLATE.md`.
8. Wait for review. Never merge your own PR.

## Setup

```bash
just install     # install all deps (Rust + Python + Node)
just verify      # confirm baseline green
```

## Workflow

### 1. Pick (or create) a task

Look in `docs/tasks/`. Every task file has sections: **Context**, **Scope: files to touch**, **Acceptance Criteria**, **Definition of Done**, **Escalation**, **Verification**. If no task exists for what you want to do, open one first and get it reviewed.

### 2. Branch

Pattern: `<type>/JAM-XXXX-<slug>` where `type` is one of `feat | fix | chore | refactor | docs | test`. Example: `feat/JAM-0042-vad-gate`.

### 3. Test, then implement

See [`docs/conventions/TEST_STRATEGY.md`](./docs/conventions/TEST_STRATEGY.md) §"TDD workflow".

### 4. Commit

Conventional Commits subject. Body explains the **why**, not the what (the diff shows the what).

### 5. PR

Use `.github/PULL_REQUEST_TEMPLATE.md`. Link the task file (`Closes JAM-0042`). Paste `just verify` output. Mark the risk checklist honestly.

### 6. Review

Wait for at least one CODEOWNERS approval. CI must be green. Linear history preferred. PR comments use the [Conventional Comments labels](./docs/conventions/CONVENTIONAL_COMMENTS.md) (`nitpick:`, `suggestion:`, `issue:`, etc.).

## Decision boundaries

See [`AGENTS.md` §"Boundaries"](./AGENTS.md) for the canonical decision-boundaries table (what an agent decides alone vs. what needs `@ipc-owner` / `@tooling-owner` review). This file defers to AGENTS.md to avoid drift — humans picking up a task should still read AGENTS.md for the latest rules.

## Definition of Done (every task)

- [ ] All Acceptance Criteria in the task file are checked
- [ ] `just verify` exits 0 locally
- [ ] `just verify-ci` exits 0 (or run CI; if known-known failure, document why)
- [ ] Coverage thresholds in `docs/conventions/TEST_STRATEGY.md` not regressed for affected crates
- [ ] `CHANGELOG.md` updated under "Unreleased"
- [ ] PR opened using template, CI green
- [ ] At least one CODEOWNERS reviewer requested
- [ ] Task file's `status` updated to `closed` after merge

## Code style

- **Python:** `ruff format`, `ruff check`, `mypy --strict` (see `STYLE.md`)
- **Rust:** `cargo clippy -- -D warnings`, `rustfmt`
- **TypeScript:** the project's linter (see `app/`)
- **Comments:** only for non-obvious **why**, never for **what** (see `STYLE.md`)
- **TODO comments:** must include owner + ticket — `# TODO(@alice, JAM-0100): ...`
- **Comments hygiene:** AI-authored inline comments that restate the next line are stripped before commit

## Safety

Four independent layers block destructive operations:

1. Local pre-commit hooks (`.pre-commit-config.yaml`)
2. Claude Code `PreToolUse` hook (`.claude/hooks/block-destructive.sh`)
3. `dcg` (destructive_command_guard) standalone scanner
4. Server-side: GitHub branch protection + `CODEOWNERS` + PR template

Destructive commands (`rm -rf`, `git reset --hard`, force-pushes, database drops) are blocked at every layer. See [`.claude/hooks/block-destructive.sh`](./.claude/hooks/block-destructive.sh).

## Security reports

See [SECURITY.md](./SECURITY.md) for how to report a vulnerability.
