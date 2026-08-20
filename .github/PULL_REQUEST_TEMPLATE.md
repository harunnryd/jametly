<!--
Thanks for contributing to jametly. AI agents: read AGENTS.md first.
Fill every checkbox honestly. Mark N/A sections with "n/a (justification)".
Use Conventional Comments labels for review feedback (see docs/conventions/CONVENTIONAL_COMMENTS.md).
-->

## What

<!-- One-paragraph summary of the change. -->

Closes JAM-XXXX

## Verification

- [ ] `just verify` exits 0 — paste the final 30 lines below
- [ ] `just verify-ci` exits 0 once (CI parity) — paste the final 30 lines below
- [ ] Tests were written **red first, then made green** (TDD Three Rules; see `docs/conventions/TEST_STRATEGY.md`)
- [ ] New tests added (coverage ≥ crate threshold per `TEST_STRATEGY.md` §2)
- [ ] No new dependency without justification in the body
- [ ] No AI-authored restate-the-code comments in the diff (per `STYLE.md`)

```
<paste `just verify` output here>
```

```
<paste `just verify-ci` output here>
```

## Risk

<!-- Mark every applicable item. If unsure, treat as applicable. -->

- [ ] No IPC contract change (`shared/schemas/ipc/v1.json` untouched)
- [ ] No public API change
- [ ] No new crate or pip dep
- [ ] No new Tauri plugin / global-shortcut binding
- [ ] No new entitlement / Info.plist key
- [ ] No new OS-specific code path (audio capture, window styling)
- [ ] No change to `docs/decisions/*` (if changed, link the new ADR)
- [ ] No new `tests/property/` invariants without a corresponding ADR or comment in `TEST_STRATEGY.md`
- [ ] No change to `shared/schemas/` (if changed, link the migration plan)

## Checklist

- [ ] Linked task file: `docs/tasks/JAM-XXXX.md`
- [ ] All AC items in the task file checked
- [ ] DoD section in the task file fully checked
- [ ] `CHANGELOG.md` updated under "Unreleased"
- [ ] Branch name follows `<type>/JAM-XXXX-<slug>` pattern
- [ ] Commit subject follows Conventional Commits (`<type>(<scope>): <subject>`)
- [ ] At least one CODEOWNERS reviewer requested
- [ ] PR-review comments use [Conventional Comments](../docs/conventions/CONVENTIONAL_COMMENTS.md) labels

## Test plan

<!-- What you tested by hand (if anything) beyond `just verify`. -->

## Screenshots / recordings

<!-- If the change is user-facing, attach a screenshot or short recording. -->
