---
status: accepted
date: 2026-08-20
---

# 0004 — MIT license for the code, "jametly" trademark reserved separately

## Context and problem statement

What license do we ship the code under?

## Decision drivers

- jametly is a personal-tool aesthetic. Friction kills adoption. A permissive, well-understood license helps.
- The "jametly" name and logo are reusable identifiers that should not be silently granted to fork-and-rebrand scenarios (this is the trap that bit the Monas→Trinity incident in typography).
- We do not want any open-source license that requires derivative source publication or restricts commercial use, but we also don't want a copyleft license because (a) we'd be saddling derivatives with the same license, and (b) consumers of the code (CEOs in the meeting room) don't care about license minimalism.

## Considered options

**A. MIT.** Permissive. Anyone can do anything. "jametly" trademark protected separately under common law + future filing.

**B. Apache-2.0.** Adds explicit patent grant. Slightly more boilerplate.

**C. BSD-3-Clause.** Similar to MIT but with an endorsement clause.

**D. GPL-3.0.** Copyleft; derivative code must remain GPL. Interferes with closed commercial derivatives.

**E. AGPL-3.0.** Copyleft + network clause. Specifically hostile to SaaS re-hosting.

**F. BSL / source-available.** Rejecting this — research on the `natively-cluely-ai-assistant` codebase showed their Personal Use Source License frustrates consumers.

## Decision outcome

Chosen option: **A — MIT for code**, with a separate `TRADEMARKS.md` reserving the "jametly" name and logo.

This mirrors the pattern used by Bun, Astro, and the Linux Foundation: free for the code, protected for the brand.

### Consequences

- **Good:** minimum friction for legitimate forks.
- **Good:** trademark reserved without restricting legitimate use; derivative works just can't call themselves "jametly".
- **Good:** standard "MIT-licensed" badge reads instantly to anyone evaluating the project.
- **Bad:** patent grant absent. Acceptable because we don't expect the core surface to be a patent minefield; revisit if we add stealth primitives that interact with macOS private APIs.
- **Bad:** trademark enforcement requires legal bandwidth we don't have day-1. Best-effort based on common-law + (eventually) USPTO filing.

## References

- License != Trademark: https://www.forrester.com/blogs/open-source-doesnt-mean-a-trademark-free-for-all/
- Bun license: https://github.com/oven-sh/bun/blob/main/LICENSE.md (text includes the trademark paragraph)
- Monas→Trinity C&D case: https://www.reddit.com/r/typography/comments/5cuumh/trinity_font_was_originally_called_monas_there_was/
- `natively-cluely-ai-assistant/LICENSE` (this monorepo) — counter-example: too restrictive
