# Tasks

One file per active task. Filename: `JAM-XXXX-slug.md` where `XXXX` is a 4-digit zero-padded ID.

## Picking up a task (for AI agents)

1. Read the task file in full.
2. Confirm `status: ready`. If `in_progress`, the task belongs to someone else — STOP and report.
3. **Read [`docs/conventions/TEST_STRATEGY.md`](../conventions/TEST_STRATEGY.md) before writing any code.** This project is TDD-first.
4. Run `just verify` on a clean tree to confirm baseline green.
5. Create the branch: `git switch -c feat/JAM-XXXX-<slug>` (or `fix/`, `chore/`, `refactor/`, `docs/`, `test/`).
6. **Red.** For each AC, write the smallest failing test that captures it. Run it. Confirm failure.
7. **Green.** Write the minimum code to pass each test.
8. **Refactor.** Cleanup. All tests stay green.
9. Run `just verify`. Must exit 0. Run `just verify-ci` once for CI parity.
10. Update the task file: `status: in_progress`, check off AC items as you complete them.
11. Open a PR using `.github/PULL_REQUEST_TEMPLATE.md`. Body: `Closes JAM-XXXX` + paste `just verify` + `just verify-ci` output + risk checklist.
12. STOP. Do not merge.
13. **Strip AI-authored restate-the-code comments from your diff.** See `STYLE.md` "AI-authored comments" + `.claude/hooks/strip-restate-comments.sh`.
14. Set the task `status: closed` once the PR merges.

The `.claude/commands/task.md` slash command automates this flow.

## Picking up a task (for humans)

Same flow. The task file's Definition of Done + the risk checklist in the PR template cover the reviewable surface; your reviewer checks against the AC list.

## Definition of Done inheritance

The Definition of Done in [`TEMPLATE.md`](./TEMPLATE.md) is normative for every task. A task file may list additional task-specific completion checks in its own `## Definition of Done` section; those checks supplement and never replace the template requirements for red-first tests, verification, coverage, changelog, PR review, CODEOWNERS, and closing the task after merge.

## Picking up an unowned gap

If you have a meaningful unit of work that's not in this directory yet, **start the task file** with:

```bash
cp docs/tasks/TEMPLATE.md docs/tasks/JAM-XXXX-my-slug.md
# edit in your branch
```

Use the next free ID (`JAM-0001`, `JAM-0002`, …). Keep IDs monotonically increasing — search `docs/tasks/` for the current max.

## Escalation taxonomy

| Tag | Meaning |
|---|---|
| `status: ready` | Open for pickup |
| `status: in_progress` | Assigned; check the task file's `assigned-to` field |
| `status: blocked` | Cannot proceed; see the task body's `## Blocked by` section |
| `status: closed` | Merged; never re-opened without an ADR |

## When tasks grow

If a single task file's `Scope` exceeds ~1 day of work for one agent, **split it** into a parent (epic) and children:

```
JAM-0042-vad-gate.md              (epic)
JAM-0043-silero-binding.md        (child of 0042)
JAM-0044-gate-state-machine.md    (child of 0042)
```

Blockers are documented in each child's `## Blocked by` field. Do not exceed scope silently.
