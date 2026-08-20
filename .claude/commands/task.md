---
description: Pick up and execute the task file at docs/tasks/$ARGUMENTS.md end-to-end: TDD red-green, verify, open PR.
argument-hint: JAM-XXXX
allowed-tools: Read, Glob, Grep, Bash(uv *), Bash(cargo test*), Bash(cargo build*), Bash(just *), Bash(git status), Bash(git diff*)
---

You are picking up task **$ARGUMENTS**.

**Read [`docs/conventions/TEST_STRATEGY.md`](../../docs/conventions/TEST_STRATEGY.md) before anything else.** This is a TDD-first project.

1. Read `docs/tasks/$ARGUMENTS.md` in full. Confirm `status: ready`. If `in_progress` or `blocked`, STOP and report.
2. Read the linked design doc / ADR referenced in the task's Context section.
3. Run `just verify` on a clean tree to confirm baseline green. If it fails, STOP — the tree is in a bad state.
4. Create the branch: `git switch -c feat/$ARGUMENTS-<slug>` (read slug from the task filename).
5. **Red.** For each Acceptance Criterion, write the smallest failing test that captures it. Run it. Confirm the failure mode matches the AC.
6. **Green.** Write the minimum code that makes the failing test pass. No speculative features.
7. **Refactor.** If obvious cleanup emerges (rename, extract, comment cleanup), do it. All tests must stay green.
8. Update the task file: set `status: in_progress`, check off AC items as you complete them.
9. Run `just verify` again. Must exit 0. Run `just verify-ci` once to confirm CI parity.
10. Update `CHANGELOG.md` under "Unreleased" with a one-line summary.
11. Open a PR using `.github/PULL_REQUEST_TEMPLATE.md`. Body: `Closes $ARGUMENTS` + paste `just verify` + `just verify-ci` output + the risk checklist.
12. Do NOT merge. Set the task `status: closed` once the PR opens.
13. **Mandatory cleanup before commit:** scan your diff for comments that paraphrase the next line. Delete them.

**Escalation rules** (from `AGENTS.md`):

- Missing tool / failing install → STOP, ping `@tooling-owner`
- Need to change IPC schema → STOP, ping `@ipc-owner`
- Need a new dependency → STOP, ping `@tooling-owner`, justify in PR body
- You wrote tests AFTER the implementation → you broke the TDD Three Rules — revert the implementation and re-do as red-then-green
- Test passes locally, fails in CI → re-read CI log once; if stuck, ping `@tooling-owner`
- Task exceeds 1 day of work → STOP, split into subtasks, do not exceed scope
