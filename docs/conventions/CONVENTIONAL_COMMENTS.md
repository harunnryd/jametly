# Conventional Comments

jametly adopts the [Conventional Comments](https://conventionalcomments.org/) convention for **PR-review feedback**. This file is the one-page reference so contributors don't have to look up the spec.

## Format

```
<label> [decoration(s)]: <subject>
[discussion]
```

- **Label** is one of the canonical set below.
- **Decoration** is optional; one or more in parens, comma-separated.
- **Subject** is a single sentence. Imperative voice, no trailing period.
- **Discussion** is optional; the author's reasoning, a question, or a link.

Examples:

```
issue (security, blocking): unsanitized chunk.text concatenated into prompt.
suggestion: prefer Introduce Explaining Variable over an inline comment here.
nitpick (non-blocking): extra trailing comma in this object's last key.
question (security): does this path validate against path traversal?
```

## Labels (canonical)

| Label | Meaning |
|---|---|
| `praise:` | Highlights something positive. Try to leave at least one per review. |
| `nitpick:` | Trivial preference-based request. Non-blocking by nature. |
| `suggestion:` | Proposes an improvement. |
| `issue:` | Highlights a specific problem with the subject. |
| `todo:` | Small, trivial, necessary change. |
| `question:` | Potential concern that may or may not be relevant. |
| `thought:` | An idea that popped up from reviewing. |
| `chore:` | Simple task required to land the subject. |
| `note:` | Non-blocking highlight the reader should take note of. |
| `typo:` | Spelling correction. |
| `polish:` | Like `suggestion` — nothing wrong, just improvements. |
| `quibble:` | Like `nitpick` — trivial preference. |

## Decorations

| Decoration | Meaning |
|---|---|
| `(non-blocking)` | Should NOT prevent the subject from being accepted. |
| `(blocking)` | MUST prevent acceptance until resolved. |
| `(if-minor)` | Resolve only if the change ends up being trivial. |

Domain tags (also parens) qualify the subject area: `(security)`, `(perf)`, `(docs)`, `(tests)`, `(a11y)`, `(ux)`, `(dx)`.

## Relationship to inline code comments

These labels are **only for PR review**. Inside the code, prefer the per-file inline-comment rules in [`STYLE.md`](../../STYLE.md). When a review thread resolves into a code change, the resolved change is **not** a Conventional Comment — it's normal code review history.

## When to use which

- **`praise:`** — always, at least once per review. Doubles as positive signal in audit.
- **`nitpick:`** — formatting, naming, ordering. Solve or ignore; never block.
- **`suggestion:`** — alternative implementation patterns. Discuss before blocking.
- **`issue:`** — bugs, missing tests, security concerns. Often `(security, blocking)`.
- **`todo:`** — "this needs follow-up after merge". Almost always `(non-blocking)`.
- **`question:`** — "I want to understand but won't block". Almost always `(non-blocking)`.
- **`chore:`** — bookkeeping the author must do before merge (link a task, update a doc). Blocking.
- **`note:`** — information for the reviewer, no action required.

## Anti-patterns

- Mixing labels in one comment (`issue:suggestion: this needs fixing`) — pick one.
- All-caps label (`ISSUE: this is broken`) — labels are lowercase.
- Missing the `:` separator (`issue this is broken`).
- Decorating without parens (`[security]` is not the convention, `(security)` is).
- Decorating a label with a domain that does not apply (`(security)` on a typo).
- Using `blocking` on a `nitpick` or `praise` (breaking the spirit of the convention).
- Writing a long discussion body inside the code comment — link to a thread or ADR.

## References

- [Conventional Comments spec](https://conventionalcomments.org/)
- [Implementation examples across OSS](https://github.com/search?q=%22suggestion+%28blocking%29%22+is%3Aissue&type=code)
- Related: `STYLE.md` for the inline-comment policy this complements
