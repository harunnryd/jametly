"""End-to-end smoke for the jametly stdio bridge.

Spawns the Python sidecar as a subprocess, sends one `echo` request, and
asserts the reply round-trips. The Python sidecar is invoked via
`uv run --project ai python -m jamly` so the test does not depend on the
sidecar being installed system-wide.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_python() -> str:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("`uv` not on PATH; install https://docs.astral.sh/uv/")
    return uv


def _spawn_sidecar(uv: str, *, cwd: Path) -> subprocess.Popen:
    """Spawn the Python sidecar in its own process group so we can SIGTERM it."""
    return subprocess.Popen(
        [uv, "run", "--project", str(cwd / "ai"), "python", "-m", "jamly"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(cwd),
        start_new_session=True,
    )


def _send_recv(proc: subprocess.Popen, payload: dict, timeout: float = 10.0) -> dict:
    assert proc.stdin is not None and proc.stdout is not None
    line = json.dumps(payload) + "\n"
    proc.stdin.write(line.encode("utf-8"))
    proc.stdin.flush()

    deadline = time.monotonic() + timeout
    buf = b""
    while time.monotonic() < deadline:
        chunk = proc.stdout.readline()
        if not chunk:
            stderr_tail = proc.stderr.read1(4096).decode("utf-8", errors="replace") if proc.stderr else ""
            pytest.fail(f"sidecar closed stdout before reply. stderr tail:\n{stderr_tail}")
        buf += chunk
        if buf.endswith(b"\n"):
            break
    return json.loads(buf.decode("utf-8").strip())


def test_bridge_echo_roundtrip() -> None:
    uv = _resolve_python()
    proc = _spawn_sidecar(uv, cwd=REPO_ROOT)
    try:
        req = {"id": "req-1", "method": "echo", "params": {"x": "hi"}}
        reply = _send_recv(proc, req)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    assert reply.get("id") == "req-1", f"expected id=req-1, got {reply}"
    assert reply.get("result") == {"x": "hi"}, f"expected echoed params, got {reply}"
    assert "error" not in reply, f"unexpected error envelope on echo: {reply}"


def test_bridge_unknown_method_returns_error_envelope() -> None:
    uv = _resolve_python()
    proc = _spawn_sidecar(uv, cwd=REPO_ROOT)
    try:
        req = {"id": "req-2", "method": "definitely.not.a.method", "params": {}}
        reply = _send_recv(proc, req)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    assert reply.get("id") == "req-2"
    assert "result" not in reply
    err = reply.get("error", {})
    assert err.get("code") == "INVALID_REQUEST", f"expected INVALID_REQUEST, got {err}"


def test_bridge_garbage_line_returns_parse_error() -> None:
    uv = _resolve_python()
    proc = _spawn_sidecar(uv, cwd=REPO_ROOT)
    try:
        assert proc.stdin is not None
        proc.stdin.write(b"this is not json\n")
        proc.stdin.flush()
        deadline = time.monotonic() + 10.0
        buf = b""
        while time.monotonic() < deadline:
            chunk = proc.stdout.readline()
            if chunk:
                buf += chunk
                if buf.endswith(b"\n"):
                    break
        reply = json.loads(buf.decode("utf-8").strip())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    err = reply.get("error", {})
    assert err.get("code") == "PARSE_ERROR", f"expected PARSE_ERROR, got {err}"


@pytest.mark.skipif(
    os.environ.get("JAMETLY_SKIP_HEAVY") == "1",
    reason="slow-sidecar smoke; set JAMETLY_SKIP_HEAVY=1 to skip on local",
)
def test_bridge_handles_sequential_requests() -> None:
    """The sidecar must keep state across requests (no early-exit, no per-request restart)."""
    uv = _resolve_python()
    proc = _spawn_sidecar(uv, cwd=REPO_ROOT)
    try:
        for i in range(5):
            req = {"id": f"req-{i}", "method": "echo", "params": {"i": i}}
            reply = _send_recv(proc, req)
            assert reply["id"] == f"req-{i}"
            assert reply["result"] == {"i": i}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
