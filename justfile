set dotenv-load
set positional-arguments
set unstable

# ----------------------------------------------------------------------------
# jametly — single ergonomic command surface
#
# Run `just` or `just --list` to see all available recipes.
# The 4-tier verify ladder is the project's only command gate.
# See docs/conventions/TEST_STRATEGY.md for what each tier covers.
# ----------------------------------------------------------------------------

# ---- meta ----------------------------------------------------------------

default:
    @just --list

# Show project version + commit SHA if in a git repo
version:
    @echo "jametly 0.0.0 (dev)"
    @git rev-parse --short HEAD 2>/dev/null || echo "(no git)"

# ---- setup ---------------------------------------------------------------

install:
    @echo "Installing Python deps via uv..."
    uv sync --all-extras
    @echo "Installing Node deps via pnpm..."
    pnpm install --frozen-lockfile
    @echo "Installing Rust deps via cargo..."
    cargo fetch --workspace
    @echo "Installing pre-commit hooks..."
    pre-commit install
    @echo "DONE."

# ========================================================================
# THE 4-TIER VERIFY LADDER
# ========================================================================

# Tier 0 — PR gate (≤ 3 min). Every commit. Lint + fast unit.
verify: rust-test-fast py-test-fast
    @echo ""
    @echo "================ verify: ALL GREEN ================"

# Tier 1 — CI parity (≤ 12 min). Every PR. + coverage + macOS e2e.
verify-ci: verify py-test-cov cov-rust e2e-mac
    @echo ""
    @echo "================ verify-ci: ALL GREEN ================"

# Tier 2 — nightly (≤ 60 min). Weekly cron. + mutation + hypothesis + perf.
verify-strict: verify-ci py-hypothesis mutants-fast py-bench
    @echo ""
    @echo "================ verify-strict: ALL GREEN ================"

# Tier 3 — release (unlimited). Manual workflow_dispatch on tag push.
verify-full: verify-strict proptest-rust py-test-parallel
    @echo ""
    @echo "================ verify-full: ALL GREEN ================"

# Original `ci` recipe stays as alias for `verify-ci` for backward compat.
ci: verify-ci

# ---- per-task shortcut (extend as needed; never bypass the gate) ----
verify-jam-XXXX:
    uv run pytest -q --no-header
    cargo nextest run --workspace --no-fail-fast || cargo test --workspace

# ---- lint / format -------------------------------------------------------

# Fast subset for the PR gate (no typecheck)
lint-fast:
    cargo fmt --all -- --check

# Strict subset for CI (includes typecheck + clippy + bandit)
lint:
    lint-fast
    uv run mypy ai/
    cargo clippy --workspace --all-targets -- -D warnings

# Auto-fix what can be auto-fixed
fix:
    uv run ruff check --fix .
    uv run ruff format .
    cargo fmt --all
    cargo clippy --workspace --fix --allow-dirty --allow-staged

# ---- Python (test runner framework) --------------------------------------

py-install:
    uv sync --all-extras

# Fast subset (skip slow markers)
py-test-fast:
    uv run pytest -q --no-header -m "not slow and not network"

# Full pytest (incl. slow + cassette replay)
py-test target="":
    uv run pytest {{target}} -q --no-header

# Coverage gated against ai/ thresholds
py-test-cov:
    uv run pytest --cov=jamly --cov-branch --cov-fail-under=70 -q --no-header

# Property-based invariants
py-hypothesis:
    uv run pytest tests/property/ -p hypothesis --hypothesis-show-statistics -q --no-header

# Parallel run
py-test-parallel workers="auto":
    uv run pytest -n {{workers}} --dist=loadfile -q --no-header

# Benchmark
py-bench:
    uv run pytest tests/perf --benchmark-only --benchmark-min-rounds=5 --benchmark-columns=min,median,stddev

# ---- Rust (test runner framework) -----------------------------------------

# Fast subset
rust-test-fast:
    cargo nextest run --workspace --all-features --no-fail-fast || cargo test --workspace --all-features

# Full test run
rust-test name="":
    cargo nextest run --workspace {{name}} || cargo test --workspace {{name}}

# Mutation test (Tier 2+)
mutants-fast:
    cargo mutants --workspace --timeout 60 --regressions --no-shuffle -j $(nproc) || true

# Property fuzzing (Tier 3)
proptest-rust:
    cargo test --workspace --features proptest-verbose -- --include-ignored proptest

# Lints
rust-lint:
    cargo clippy --workspace --all-targets -- -D warnings

# Docs
rust-doc:
    cargo doc --workspace --no-deps

# ---- per-task shortcuts (extend as needed; never bypass the gate) ----

# Phase 0: skeleton bridge — proves the stdio JSON-RPC + NDJSON spine.
verify-jam-0001:
    cargo test -p ipc-proto
    uv run --project ai pytest tests/integration/test_bridge_echo.py -v
    cargo test -p jametly -- --nocapture

# Phase 1 audio contract: dependency-free abstraction and deterministic mock.
verify-jam-0004:
    cargo test -p audio-backend -- --nocapture
    cargo clippy -p audio-backend --all-targets -- -D warnings

# Screen capture contract: region validation, blob storage, cleanup, and deterministic mock.
verify-jam-0005:
    cargo test -p screen-capture -- --nocapture
    cargo clippy -p screen-capture --all-targets -- -D warnings

# Secure configuration contract: namespace validation, fake store, and config model.
verify-jam-0006:
    cargo test -p secure-store -- --nocapture
    cargo clippy -p secure-store --all-targets -- -D warnings
    uv run pytest tests/unit/test_config.py -q --no-header

# SQLite store contract: migrations, repositories, FTS5 search, and rollback.
verify-jam-0007:
    uv run pytest tests/unit/test_db.py tests/integration/test_db_roundtrip.py -q --no-header

# Phase 0: full-duplex IPC — events and replies share one stdout stream.
verify-jam-0002:
    cargo test -p ipc-proto
    uv run pytest tests/unit/test_sidecar.py -v
    uv run pytest tests/integration/test_bridge_events.py -v
    cargo test -p jametly -- --nocapture

# Phase 0: async sidecar runtime — concurrent dispatch and cancellation.
verify-jam-0003:
    uv run pytest tests/unit/test_async_bridge.py -v
    uv run pytest tests/integration/test_bridge_async.py -v
    uv run pytest tests/unit/test_sidecar.py tests/integration/test_bridge_events.py -v

# Local STT pipeline: chunk ordering, VAD drain, partial/final events, and typed errors.
verify-jam-0008:
    uv run pytest tests/unit/test_stt.py -q --no-header
    uv run pytest tests/property/test_audio_chunker.py -q --no-header
    uv run pytest tests/integration/test_stt_pipeline.py -q --no-header

# ---- coverage -------------------------------------------------------------

cov-rust:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p target/coverage
    if command -v rustup >/dev/null 2>&1; then
        cargo llvm-cov --workspace --all-features --lcov --output-path target/coverage/rust.lcov
        cargo llvm-cov --workspace --html --output-dir target/coverage/html
    else
        llvm_root="$(brew --prefix llvm)"
        LLVM_COV="$llvm_root/bin/llvm-cov" LLVM_PROFDATA="$llvm_root/bin/llvm-profdata" \
            cargo llvm-cov --workspace --all-features --lcov --output-path target/coverage/rust.lcov
        LLVM_COV="$llvm_root/bin/llvm-cov" LLVM_PROFDATA="$llvm_root/bin/llvm-profdata" \
            cargo llvm-cov --workspace --html --output-dir target/coverage/html
    fi

# ---- Tauri e2e (macOS only by default) ------------------------------------

e2e-smoke:
    @echo "Starting Tauri dev server in background..."
    cargo tauri dev --no-watch &
    @sleep 8
    @echo "Running smoke tests..."
    uv run pytest tests/e2e -v
    @cleanup

e2e-mac:
    uv run pytest tests/integration/test_bridge_echo.py -v

# ---- security -------------------------------------------------------------

audit:
    cargo audit
    uv run pip-audit
    @echo "If vulnerabilities found, see SECURITY.md for disclosure."

# ---- stealth (gated on JAMETLY_STEALTH_E2E=1) ------------------------------

stealth-verify:
    @echo "Stealth verification requires JAMETLY_STEALTH_E2E=1"
    test -n "$$JAMETLY_STEALTH_E2E" || (echo "Set JAMETLY_STEALTH_E2E=1 to run" && exit 1)
    uv run pytest tests/stealth -v

# ---- cleanup -------------------------------------------------------------

clean:
    cargo clean
    rm -rf ai/.venv
    rm -rf node_modules
    rm -rf dist

# ---- internal helpers ----------------------------------------------------

cleanup:
    -@pkill -f "tauri dev" || true
    -@pkill -f "cargo tauri" || true
