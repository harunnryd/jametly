# Changelog

All notable changes to jametly are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Phase 0 skeleton bridge** (`JAM-0001-stdio-bridge`): `core/ipc-proto` (serde envelope types), `ai/src/jamly` (Python sidecar with `echo` + error envelopes), `src-tauri` (Tauri shell + `bridge::Sidecar` via `tokio::process::Command`). 13 Rust contract tests + 4 Python integration tests pass. Verified manually: echo, unknown-method, malformed-JSON paths all produce canonical wire output.
- **GOAL.md** — mission + 5 architectural lines (immutable) + non-goals + 2-part north-star test (invisibility + recall). Source of truth for the architectural commitments.
- Day-0 repo scaffold: meta files (LICENSE, README, AGENTS, CONTRIBUTING, STYLE, SECURITY, TRADEMARKS, CHANGELOG, GOAL), .claude/ ops config (settings + commands + hooks), docs/ (architecture + decisions + tasks + **conventions**), justfile (tiered `verify` / `verify-ci` / `verify-strict` / `verify-full`), CODEOWNERS, .pre-commit-config.yaml (ruff + guard + `dcg` + comment-density), .github/ (PR + issue templates + CI), workspace manifests (package.json, pnpm-workspace.yaml, Cargo.toml, pyproject.toml, tauri.conf.json)
- **docs/conventions/TEST_STRATEGY.md**: per-substack test layer-mix, tooling picks, coverage thresholds, mutation testing schedule, AI/LLM eval tooling (DeepEval + LangSmith), 2-tier confidence model
- **docs/conventions/CONVENTIONAL_COMMENTS.md**: PR-review label convention (12 labels × 3 decorations × 7 domain tags)
- `docs/decisions/0001..0006`: 6 MADR-format ADRs (Tauri over Electron, Python AI sidecar, stdio IPC, MIT + trademark, OSS no Pro tier, macOS stealth honest disclosure)
- `docs/architecture/{00-overview,01-ipc,02-modules}`: single ASCII diagram + full IPC method list + module map

### Changed
- README.md: "no cloud calls" wording reconciled with SECURITY.md "model downloads OK" (model downloads are user-key configured, link to SECURITY §Privacy posture).
- `docs/decisions/0006-macos-stealth-honest-disclosure.md` + SECURITY.md: stealth tiers renamed from "Tier 0/1/2" → "Band A/B/C" to eliminate word collision with the verify ladder (`verify`/`verify-ci`/`verify-strict`/`verify-full`).
- `tauri.conf.json`: `minimumSystemVersion` 10.15 → 13.0 to match the bug-report envelope.
- `docs/architecture/01-ipc.md`: sidecar binary `pluely-ai-sidecar` → `jametly-ai-sidecar`.
- AGENTS.md, CONTRIBUTING.md, STYLE.md: minor trim, link to canonical sources instead of duplicating tables.

### Removed
- `docs/decisions/0001..0006.md`: scrubbed stale references to a non-existent ADR-0007.
- `docs/decisions/0001..0006.md`: scrubbed "Pluely" mentions → "predecessor codebase".
- CHANGELOG.md: removed stale "Pre-day-0 scaffolding" + "Migration from jametly-v1" sections (v1 is gone; this dir is the rebuild).

### Fixed
- SECURITY.md: dropped dangling `docs/decisions/0007-security-contact.md` forward reference.
- `.claude/settings.json`: tightened dangerous allow-list (`format *` anchored, dead `.drop*` removed, `launchctl*`/`systemctl*` moved to `deny`, `chmod 777` + `gh repo {delete,edit}*` denied).

### Security
- See SECURITY.md for the privacy posture and macOS stealth disclosure.

