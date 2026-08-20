# jametly — Claude Code overrides

The full project rules live in [`AGENTS.md`](../AGENTS.md) and [`docs/conventions/TEST_STRATEGY.md`](../docs/conventions/TEST_STRATEGY.md). This file is for Claude Code-specific behavior only — do not duplicate the agent rules here.

## Skills to use automatically

- **`superpowers:using-superpowers`** — at the start of every conversation
- **`superpowers:brainstorming`** — before any creative work (features, components, behavior changes)
- **`superpowers:dispatching-parallel-agents`** — when facing 3+ independent tasks
- **`superpowers:test-driven-development`** — before writing implementation code
- **`superpowers:systematic-debugging`** — before proposing any bugfix
- **`superpowers:verification-before-completion`** — before claiming work complete
- **`superpowers:writing-plans`** — when given a multi-step spec before code

## Sub-agent preference

- Use `general-purpose` for any parallel investigation; use `Explore` for read-only search.
- Multiple sub-agents in a single message = parallel execution.

## Comment policy

- Inline comments restating the next line are noise. Delete before commit.
- Beck's test applies: *add a comment you wish you had when reading the code / remove a comment that just says what the code says*.
- AI-generated comments restating code: strip before commit.

## Memory pointers

- Persistent project memory is in `~/.claude/projects/.../memory/MEMORY.md` (out-of-repo).
- The repo's instructions live in `AGENTS.md`, `STYLE.md`, `docs/conventions/`, and `docs/architecture/`. Read those, not the memory file, for project rules.
- If the user invokes a slash command like `/verify`, `/test`, or `/task`, see `.claude/commands/`.

## Verification gate

The agent's single command gate is `just verify`. The four-tier ladder:

| Gate | Command | When | Budget |
|---|---|---|---|
| Local PR gate | `just verify` | every commit | ≤ 3 min |
| CI parity | `just verify-ci` | every PR / pre-merge | ≤ 12 min |
| Nightly | `just verify-strict` | Monday cron | ≤ 60 min |
| Release | `just verify-full` | tag push | unlimited (manual) |

Do not bypass. If you think there's a reason to skip it, write that reason in the PR body and ping `@tooling-owner`.

## Hard stop (do not proceed)

- If `just verify` fails, do not claim the task done.
- If you edited the IPC schema without pinging `@ipc-owner`, revert and start over.
- If you added a dependency without justification, revert.
- If you wrote a test AFTER the implementation, you broke the TDD Three Rules — revert the implementation and re-do as red-then-green.
- If a comment paraphrases the next line, delete it.
