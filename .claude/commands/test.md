---
description: Run a specific test (Python or Rust) and report the result.
argument-hint: <py|rust|path/to/test>
allowed-tools: Bash(uv *), Bash(cargo test*), Bash(just *)
---

You are running a targeted test.

1. Parse `$ARGUMENTS`. The first token is the language (`py` or `rust`); the rest is the path or test name.
2. If language is `py`: run `uv run pytest <path> -q --no-header`.
3. If language is `rust`: run `cargo nextest run --workspace --no-fail-fast -- <name>` (fallback to `cargo test --workspace -- <name>` if nextest isn't installed yet).
4. If language is omitted: treat the rest as a `just` recipe name (e.g. `just test audio`).
5. Paste the final 30 lines of output.
6. If the test fails, run `pytest -x --tb=short` (or `cargo test -- --nocapture`) to capture the first failure cleanly.

For snapshot tests (`syrupy`, `insta`):

- If the failure is a snapshot mismatch you *expected*: re-run with `--snapshot-update` (Python) or `cargo insta accept` (Rust).
- If the failure is unexpected: STOP. Do not auto-accept. Report the diff to the user.

For property tests (`hypothesis`, `proptest`):

- Counterexamples are auto-shrunk — paste the minimal failing case in the report.
- If the same counterexample appears twice: convert to a regression example (`@example`) in the test file.
