---
description: Run the project's tiered verify gate. Use after any change to confirm baseline green.
argument-hint: (optional tier name: verify | verify-ci | verify-strict | verify-full)
allowed-tools: Bash(just *), Bash(uv *), Bash(cargo *), Bash(cargo test*)
---

You are running the project's verify gate.

1. Default tier is `verify` (fast PR gate). Honor any `$ARGUMENTS` override.
2. Run `just $ARGUMENTS` (or `just verify` if empty).
3. Paste the final 30 lines of output verbatim.
4. If anything fails, stop. Do not retry. Report the failure to the user.
5. If everything passes, confirm with: `just $ARGUMENTS: PASS` and the elapsed time.

Tier ladder (see `justfile` for definitions):

| Tier | Command | Budget | When |
|---|---|---|---|
| Local PR gate | `just verify` | ≤ 3 min | every commit |
| CI parity | `just verify-ci` | ≤ 12 min | every PR |
| Nightly | `just verify-strict` | ≤ 60 min | Monday cron |
| Release | `just verify-full` | unlimited | tag push |

If the user asks "does this work?", run `just verify` and stop. If they ask "does this work for a release?", run `just verify-full`.
