# jametly code style

One page. No fluff. Tests live in [`docs/conventions/TEST_STRATEGY.md`](./docs/conventions/TEST_STRATEGY.md), not in this file.

## Python (`ai/`)

| Tool | Enforces |
|---|---|
| `ruff format` | Black-compatible formatting, line-length 100 |
| `ruff check` | pycodestyle, pyflakes, isort, bugbear, comprehensions, pyupgrade |
| `mypy --strict` | All functions annotated. `disallow_untyped_defs = true` |

### Rules

- One sentence per public function — `Args:` / `Returns:` / `Raises:` only when non-obvious.
- Module docstring required if file > 50 LOC. First line = purpose. Second line = when **not** to use it.
- Imports grouped: stdlib → third-party → first-party (`jamly`), separated by blank line.
- `from __future__ import annotations` at the top of every module.
- Type hints on every public signature.
- `# inline comment` only when the code looks wrong but is intentionally right.
- `TODO` comments must include owner + ticket: `# TODO(@alice, JAM-0100): ...`.
- No bare `except:`. Catch specific exceptions. Re-raise or log + handle, never silently swallow.
- Prefer `pydantic.BaseModel` over `dataclass` for anything crossing an IPC boundary.
- Prefer `pathlib.Path` over `os.path`.

## Rust (`src-tauri/`, `core/`)

| Tool | Enforces |
|---|---|
| `rustfmt` | Standard formatting |
| `cargo clippy -- -D warnings` | All clippy warnings are errors |
| `cargo doc --no-deps` | Doc comments generate cleanly |

### Rules

- One sentence per public function. Module-level `//!` doc on files > 50 LOC.
- No `unsafe` without a `// SAFETY:` comment explaining the invariant.
- Errors implement `std::error::Error`. No `String` for typed errors — use `thiserror` enums.
- Prefer `&str` over `String` parameters, `impl AsRef<Path>` over `&Path`.
- All public items MUST be documented. `#![deny(missing_docs)]` enabled per crate.
- `cargo build --release` flags treated as bugs: `unused`, `dead_code`, `warnings`.

## TypeScript (`app/`)

- `prettier` (default config) + `eslint` (typescript-eslint strict).
- Functional components + hooks. No class components.
- `as const` for literal types. `unknown` over `any`.
- File naming: `PascalCase.tsx` for components, `camelCase.ts` for hooks/utils.

## Comments — Must always / Must never / Situation-dependent

**Rule.** Write code that says what it does. Write a comment only for the *why* the code cannot say. If a comment fails to clear that bar, refactor the code instead.

### Must always

1. **A comment explains a `why` the code cannot say** — workaround, external constraint, performance trade-off, intent behind a non-obvious choice.
   *Citations:* Martin ch. 4 "good comments"; Ousterhout ch. 13; Beck *Tidy First?* ch. 12; McConnell *Code Complete* checklist.

2. **Public-API docs on every Python public module/function/class/method** and **`#![deny(missing_docs)]` on every Rust crate's public API**. One-sentence docstring on the *recipe*; helper bodies earn silence (PEP 257).

3. **TODOs carry an owner + ticket reference.** Format: `# TODO(@alice, JAM-XXXX): ...` (Google Python §3.12 + Conventional Comments).

### Must never

1. **Comments that restate the code.** Enforced mechanically:
   - Python: `ruff check` flags obvious restate; reject in review.
   - Rust: `#![deny(clippy::doc_lazy_continuation)]` plus reviewer discipline.
2. **Comments as a substitute for renaming or extraction.** If you need a comment to explain what a block does, **extract it into a function whose name *is* the comment**. Cite: Martin ch. 4; Beck ch. 12 (*"if a comment is explaining what the code does, the tidying is Explaining Variable or Extract Method, not 'leave the comment in'"*); Hunt & Thomas (*Pragmatic Programmer*) — "Don't comment bad code — rewrite it."
3. **Mandated boilerplate, journal/attribution comments, commented-out code, position markers, closing-brace comments.** Git remembers history; the code remembers structure.

### Situation-dependent

1. **Algorithm-defined constants** (SipHash round keys, xxHash primes, RFC magic numbers, CVE offsets, IEEE-754 layout constants, RFC 3986 reserved-character tables). Name them exactly as the source does; keep **only the citation as the comment**. Do not invent "descriptive" names that hide the origin.

   ```rust
   // SipHash-2-4 round keys, Aumasson & Bernstein 2012, §2.4.
   const SIP_ROUND_KEY_0: u64 = 0x736f6d6570736575;
   ```

2. **Module/file header comments** when the abstraction is deep (Ousterhout ch. 4 + 13). For `ai/` Python modules >50 LOC and any Rust `pub` item, a one-sentence header is mandatory; longer is fine when the depth demands it.

3. **Inline end-of-line comments** for non-obvious units, magic-number meaning, or an inline TODO — never for paraphrasing the function. (Google Python §3.8.5: *"Non-obvious ones get comments at the end of the line."*)

4. **`// SAFETY:` comments** are mandatory for Rust `unsafe` blocks (Rust API Guidelines C-SAFETY).

5. **Long-form `why` (>3 lines) → link to an ADR at `docs/decisions/000N-*.md`**, don't inline. Keeps the code lean.

### AI-authored comments (2024–26)

LLM-style code systematically **over-comments** (every line annotated, often restating the obvious) because the training corpus is tutorial-heavy. Apply this filter before commit:

- A PR that adds >1 inline comment per ~10 LOC of changed code likely has restate-the-code comments. Strip them.
- A comment beginning with "First, we…", "Now we…", "This function…" is almost certainly LLM-generated noise. Delete.
- Reserve *human attention* for *why* comments and module-level docstrings.

This policy is **enforced mechanically** by `.pre-commit-config.yaml` (`comment-density-guard` + `no-restate-the-code-comments`) and `.claude/hooks/strip-restate-comments.sh`.

See [`docs/conventions/CONVENTIONAL_COMMENTS.md`](./docs/conventions/CONVENTIONAL_COMMENTS.md) for the PR-review comment-label convention.

## Commit subject format

Conventional Commits: `<type>(<scope>): <subject>`

- Types: `feat | fix | chore | refactor | docs | test | perf`
- Scopes: `audio | ipc | ai | ui | stealth | db | docs | infra`
- Subject ≤ 72 chars, imperative mood, no period

Examples:

```
feat(audio): add silero-vad gate on mic stream
fix(ipc): drop late events on chat.cancel
chore(deps): bump tauri to 2.1.0
```
