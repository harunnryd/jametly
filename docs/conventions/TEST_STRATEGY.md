# Test strategy

> Per-project TDD canon: TDD's Three Rules, pyramid-vs-trophy hybrid, per-substack layer-mix, tooling picks, 4-tier CI ladder, mutation testing schedule, AI-agent eval, anti-patterns. Refined against TDD canon (Beck, Martin, North), pyramid vs trophy (Cohn, Vocke, Dodds), AI-agent testing practice (DeepEval, LangSmith, Ragas), Tauri+Python tooling (Context7-verified).

## 1. Philosophy

### 1.1 TDD's Three Rules

Codified by Robert C. Martin from his 1999 pairing with Kent Beck:

1. You must write a failing test before you write any production code.
2. You must not write more of a test than is sufficient to fail, or fail to compile.
3. You must not write more production code than is sufficient to make the currently failing test pass.

The driving cycle is **Red → Green → Refactor** (Beck, *TDD by Example*, 2002).

**jametly posture:** TDD is the default for every public command/API surface and every core domain function. Skip TDD only where it doesn't help (see §2).

### 1.2 Pyramid vs Trophy (Cohn → Vocke → Dodds → modern consensus)

| | Pyramid | Trophy | Modern hybrid |
|---|---|---|---|
| **Shape** | Wide unit base, narrow E2E apex | Wide integration, lighter unit | Depends on subsystem |
| **Best for** | Pure backends where "unit" is meaningful | SPAs / LLMs / distributed-systems where smallest contract is the integration | Context-dependent |
| **Per-layer rule** | "More high-level → fewer tests" | "Don't over-mock at the unit layer — tests lose confidence" | "Cheap real tests beat expensive fake tests" |

**The consensus** is to stop arguing about shape and pick **layer-mix based on cost-per-confidence for *your* system**.

### 1.3 Property-based testing (Hypothesis, proptest)

Where invariants exist, write them as properties (not examples). The framework generates random inputs and shrinks to minimal counterexamples.

**jametly properties:**
- IPC envelope parser: random NDJSON byte streams always produce a valid `Envelope` or a typed error code (never a panic).
- STT: `transcribe(pcm_blob)` completes within N seconds for any PCM input.
- SqliteStore: append-then-search round-trips perfectly; FTS5 + vec0 results agree.
- Audio chunker: `chunk(audio, max_seconds=N)` total ≈ original duration; no chunk exceeds N.

### 1.4 Mutation testing (cargo-mutants, mutmut)

Coverage measures *whether* a line ran. Mutation score measures *whether your tests would catch a bug*. Run on the Rust core crates via weekly cron (`cargo-mutants`); aim for mutation score ≥ 70% on `core/ipc-proto` and `core/sqlite-store`. **Not on every PR** — too slow.

### 1.5 BDD / Gherkin at the public surface

For the **outer loop** (CLI commands, Tauri command surface), a thin Gherkin layer (pytest-bdd / behave) per CLI command pays off — stakeholders can read the spec. For the **inner loop** (Whisper wrapper, JSON parsing, audio chunking), plain pytest is cheaper.

---

## 2. Layer-mix per substack

### 2a. Rust core crates — pyramid-heavy

`core/{audio-backend, screen-capture, sqlite-store, ipc-proto, secure-store}`. Deterministic, pure-Rust, no network.

| Layer | Mix | Notes |
|---|---|---|
| Unit | **~80%** | Pure codec math, schema validation, serde round-trips, ringbuffer invariants. `cargo nextest run` per crate. |
| Integration | ~15% | Cross-module interactions (audio frame → sqlite write; IPC envelope → handler dispatch). Use `cargo test --tests`. |
| E2E | ~5% | Tauri command surface only — verified again by the Tauri E2E layer below. |

### 2b. `src-tauri/commands` — pyramid with mock runtime

These are thin handlers, but the IPC envelope is the contract worth testing.

| Layer | Mix | Notes |
|---|---|---|
| Unit | ~70% | Argument validation, error mapping, handler dispatch. Mock concrete types where possible. |
| Integration (narrow) | ~20% | Use `tauri::test::mock_app()` + `MockRuntime`. Commands must be generic over `R: Runtime`. |
| E2E | ~10% | Full app via `tauri-driver` + WebDriverIO. |

### 2c. Python AI sidecar — trophy-heavy

Most "unit" *is* integration — the LLM call is the unit boundary.

| Layer | Mix | Notes |
|---|---|---|
| Static | ~5% | `mypy --strict`, ruff, bandit. |
| Unit | ~25% | Pure Python helpers: prompt assembly, output parsing, IPC envelope construction, sqlite round-trips. Use fakes for LLM. |
| Integration | **~60%** | Real LLM (haiku) + real tools + real IPC. Recorded LLM traces as pytest cassettes. DeepEval `ToolCorrectnessMetric` on the Ask graph. |
| E2E | ~10% | Full bridge: Python sidecar spawns, Rust spawns, request/response cycle. |

### 2d. Tauri desktop binary — e2e only

Asserts user-visible journeys on the **packaged** binary, not on a dev build.

| Layer | Mix | Notes |
|---|---|---|
| Unit | 0% | UI changes too fast; the framework already tests itself. |
| E2E | 100% | 10–15 specs via `tauri-driver` + WebDriverIO + `@wdio/tauri-service` (for macOS). |

### 2e. When NOT to use TDD

- **UI rendering** → snapshot tests (`@testing-library` / Vitest snapshot). Behavior-first TDD on the React layer locks in CSS-class names.
- **Concurrency internals** → stress harnesses (`loom` for Rust; `pytest-repeat --count=N` for Python). Non-deterministic ordering makes "make this failing test pass" unstable.
- **Pure research code** (no contract yet) → test-after once the shape crystallizes.
- **One-liner utilities** → group into one parameterized test, or rely on typecheck + review.

---

## 3. Tooling

### 3a. Rust

| Tool | Purpose | Where |
|---|---|---|
| `cargo nextest` | Fast process-per-test runner (faster than libtest once ≥ 200 tests) | Default test runner in CI |
| `cargo-llvm-cov` | Source-based coverage; preferred over `cargo-tarpaulin` | `just verify-ci`, badge generation |
| `proptest` | Property-based for NDJSON envelope + sqlite round-trip | `core/ipc-proto/tests/` |
| `mockall` | `#[automock]` for `core/audio-backend` per-OS trait | Per-OS backend tests |
| `insta` | Snapshot for IPC envelopes + TOML config round-trips | `core/ipc-proto/tests/protocol_contract.rs` |
| `test-case` or `rstest` | Parameterized tests for error-code matrices | Pick one, not both. Default: `test-case`. |
| `cargo-mutants` | Mutation testing | Weekly cron in `.github/workflows/build-smoke.yml` |

### 3b. Python

| Tool | Purpose | Where |
|---|---|---|
| `pytest` + `pytest-asyncio` (asyncio_mode=auto) | Core runner | All `ai/tests/`, `tests/` |
| `pytest-xdist` | Process parallelism for CPU-bound tests | Default in `just verify` |
| `pytest-benchmark` | Perf budgets (STT first-token, VAD per-30ms-frame) | `tests/perf/` |
| `syrupy` | Snapshot for prompts + transcript exports | `tests/snapshot/` |
| `hypothesis` | Property-based invariants | `tests/property/` |
| `respx` | Mock httpx (LLM provider calls) | `tests/unit/` |
| `pytest-recording` (vcrpy) | Record + replay real LLM HTTP cassettes | `tests/cassettes/` |
| `ruff` + `mypy --strict` + `bandit` | Static tier | `just verify` |

### 3c. AI-agent evaluation

| Tool | Purpose |
|---|---|
| `langchain_core.language_models.FakeMessagesListChatModel` | Cheap LLM fake for unit tests |
| `DeepEval` (`ToolCorrectnessMetric`, `GEval`, `DAGMetric`, `BaseMetric`) | Behavior + tool-call assertions; ~$0.30 per 50-case run on gpt-4o-mini judge |
| LangSmith | Tracing + offline/online evaluators |
| `pytest-recording` (VCR) | Recorded real-LLM traces, deterministic replay |

**Tooling pick:** **DeepEval** for behavioral eval (matches LangGraph semantics). **LangSmith** for tracing. Skip Ragas (no RAG yet) and promptfoo (no A/B prompt experiments).

### 3d. Tauri E2E

| Tool | Purpose |
|---|---|
| `tauri-driver` (official) | Cross-platform WebDriver for Tauri 2 |
| `@wdio/tauri-service` | macOS embedded WebDriver (workaround: no WKWebView driver) |
| WebDriverIO | Test framework |

### 3e. Cross-stack integration pattern

`core/ipc-proto/tests/protocol_contract.rs` — Rust side asserts wire framing via `tauri::test::mock_app()` + `insta` snapshot.
`ai/tests/test_transcript_partial_event.py` — Python side asserts the typed invariant via `hypothesis`.

Both stored as snapshots — change to either side fails both layers.

---

## 4. CI tiers

The four-tier ladder maps to the four `just` recipes in [`justfile`](../../justfile):

| Tier | Command | Budget | Frequency | Coverage threshold |
|---|---|---|---|---|
| Local PR gate | `just verify` | ≤ 3 min | every commit | warning only (delta < 2%) |
| CI parity | `just verify-ci` | ≤ 12 min | every PR | **gate** |
| Nightly | `just verify-strict` | ≤ 60 min | Monday cron | gate + mutation score delta report |
| Release | `just verify-full` | unlimited | tag push | gate + full mutation suite |

### 4a. Tier 0 — `just verify` (PR gate, every commit)

```just
verify: lint-fast py-test-fast rust-test-fast
    @echo "verify: tier-0 green"
```

- Lint + fast unit tests only
- Three-strikes rule: if a Tier 0 test flakes, mark `@pytest.mark.flaky` immediately, file follow-up
- Lives in the dev loop; runs in < 3 min

### 4b. Tier 1 — `just verify-ci` (every PR)

```just
verify-ci: verify py-test-cov cov-rust e2e-mac
    @echo "verify-ci: tier-1 green"
```

- Tier 0 + coverage gates per crate + macOS-only e2e (full IPC bridge round-trip + a couple of overlay flows)
- Coverage thresholds (per crate; gate values):

  | Crate | Line | Branch |
  |---|---|---|
  | `core/ipc-proto` | 90% | 85% |
  | `core/sqlite-store` | 90% | 85% |
  | `core/secure-store` | 80% | 70% |
  | `core/audio-backend` | 60% | 50% |
  | `core/screen-capture` | 60% | 50% |
  | `src-tauri/` | 70% | 60% |
  | `ai/` | 75% | 60% |

### 4c. Tier 2 — `just verify-strict` (nightly cron)

```just
verify-strict: verify-ci py-hypothesis mutants-fast py-bench
    @echo "verify-strict: tier-2 green"
```

- Tier 1 + `hypothesis` invariants + `cargo-mutants` on Rust core crates + `pytest-benchmark` perf budgets
- Runs Monday 09:00 UTC via `.github/workflows/build-smoke.yml`
- **Time-boxed** at 60 min; cancelled if exceeds; humans investigate

### 4d. Tier 3 — `just verify-full` (release)

```just
verify-full: verify-strict proptest-rust py-test-parallel
    @echo "verify-full: tier-3 green"
```

- Tier 2 + `proptest` exhaustive crate fuzzing + `pytest -n auto` parallelism
- Manual workflow_dispatch on tag push
- Failure → block release

### 4e. CI matrix (`.github/workflows/build-smoke.yml`)

```yaml
strategy:
  fail-fast: false
  matrix:
    os: [macos-latest, windows-latest, ubuntu-latest]
    tier: [verify, verify-ci]
```

- Tier 0 + Tier 1 run on every PR; Tier 2 = nightly; Tier 3 = manual.
- macOS Tier 1 e2e runs via `@wdio/tauri-service` (embedded driver); Linux + Windows via `xvfb-run` + standard tauri-driver.

---

## 5. Anti-patterns to actively reject

- **Mock-heavy LangGraph tests** that mock the LLM and assert on `llm.invoke` call args. The mock is the system under test — guarantees nothing. Use recorded LLM traces for behavior assertions.
- **100% coverage gates in CI.** Coverage is a discovery tool (Martin Fowler's *Test Coverage* essay), not a quality metric. Tier 1 has per-crate gates; Tier 0 has warning only.
- **E2E tests that assert CSS classes** via `tauri-driver`. Test the framework, not your code.
- **Tests-as-documentation never read.** Prefer a separate `docs/` folder with high-quality examples.
- **Slow+stale integration suites** (6 min, never fails, never gets touched). Either delete or make fast.

## 6. Anti-AI-slop hygiene

Tied to `STYLE.md` "AI-authored comments":

- LLM-style code systematically **over-comments** (every line annotated, often restating the obvious).
- A pre-commit hook (`comment-density-guard`) flags files with `comment_lines / code_lines > 0.40`.
- A Claude Code `PreToolUse` hook (`strip-restate-comments.sh`) flags LLM-flavored comment prefixes ("First, we…", "Now we…", "This function…").
- Apply Beck's test in review: *add a comment you wish you had / remove a comment that just says what the code says*.

## 7. Network + dependency-gated tests

Integration tests that hit a **live external dependency** (local Ollama server, OS keychain, etc.) are annotated `@pytest.mark.network`. `just verify` runs `pytest -m "not slow and not network"`, so these tests must skip cleanly in CI without the dependency present.

**Marker discipline — per-test, not module-level.** A module-level marker skips every test in the file, including the 30+ cheap subprocess round-trips in `tests/integration/` that don't touch a real provider. Per-test markers keep the cheap layer fast while gating only the 3 tests that actually need Ollama.

**Probe-with-diagnostic on `-m network`.** When a developer runs `pytest -m network` without Ollama running, `tests/conftest.py::pytest_collection_modifyitems` does a single TCP connect to `$OLLAMA_BASE_URL` (default `http://localhost:11434`) and skips the network-marked tests with:

```
Ollama not reachable at http://localhost:11434;
set OLLAMA_BASE_URL or run `ollama serve`
```

The probe is **TCP-only**, not HTTP — it costs ~1 ms and avoids coupling to Ollama's API version. The probe runs **only when at least one collected item has the network marker**, so the common `-m "not network"` path adds zero overhead.

**Adding a new network-gated test:**
1. Decorate the test: `@pytest.mark.network`.
2. If it depends on a non-Ollama provider (e.g. a future remote API), add an explicit reachability check inside the test body — don't piggyback on the Ollama probe.
3. Run `just py-test-fast` to confirm the test is deselected. Then run `pytest -m network -v` to confirm it runs (or skips with the diagnostic) under the local config.

**Why this matters in production.** Without the marker, `just verify` spawns the sidecar → sidecar tries to connect to Ollama → connect times out at the sidecar's `wait_for(deadline_s)` ceiling → the test reports a hang instead of a skip. The marker discipline is the only thing keeping the Tier-0 PR gate under its 3-minute budget.

---

## References

- Robert C. Martin — *The Cycles of TDD* (2014) — the canonical "Three Rules" attribution
- Kent Beck — *Test-Driven Development: By Example* (2002)
- Ham Vocke — *The Practical Test Pyramid* (martinfowler.com, 2018)
- Kent C. Dodds — *Write tests. Not too many. Mostly integration.* (2017)
- Dan North — *Introducing BDD* (2006)
- Wikipedia — *Mutation testing* (score formula)
- Confident AI — *DeepEval* (`ToolCorrectnessMetric`, `GEval`, `DAGMetric`)
- LangSmith — *Evaluation concepts* (offline / online / evaluators)
- Tauri v2 docs — *Testing* guide (`tauri-driver`, `MockRuntime`)
- Project-local: `STYLE.md` (comment policy), `AGENTS.md` (escalation rules), `justfile` (canonical recipes)
