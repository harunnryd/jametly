from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _uv() -> str:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("`uv` not on PATH; install https://docs.astral.sh/uv/")
    return uv


def _spawn(home: Path) -> subprocess.Popen[bytes]:
    env = {
        **os.environ,
        "JAMETLY_HOME": str(home),
        "PYTHONPATH": str(REPO_ROOT / "ai" / "src"),
    }
    return subprocess.Popen(
        [_uv(), "run", "--project", str(REPO_ROOT / "ai"), "python", "-m", "jamly"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
        start_new_session=True,
        env=env,
    )


def _send(proc: subprocess.Popen[bytes], payload: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
    proc.stdin.flush()


def _read_reply(proc: subprocess.Popen[bytes], timeout: float = 40.0) -> dict:
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    while True:
        if time.monotonic() >= deadline:
            pytest.fail("timed out waiting for a reply")
        raw = proc.stdout.readline()
        if not raw:
            pytest.fail("sidecar closed stdout before replying")
        line = json.loads(raw.decode("utf-8").strip())
        if "result" in line or "error" in line:
            return line


def _teardown(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        proc.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)
    for handle in (proc.stdin, proc.stdout, proc.stderr):
        if handle is not None:
            with contextlib.suppress(Exception):
                handle.close()


def test_the_sidecar_announces_its_process_identity_on_startup(tmp_path: Path) -> None:
    proc = _spawn(tmp_path)
    try:
        _send(proc, {"id": "r1", "method": "debug.echo", "params": {"value": 1}})
        _read_reply(proc)

        assert proc.stdin is not None
        proc.stdin.close()
        assert proc.wait(timeout=30) == 0

        assert proc.stderr is not None
        stderr = proc.stderr.read().decode("utf-8", "replace")
        assert "sidecar ready" in stderr

        announced = re.search(r"pid=(\d+)", stderr)
        assert announced is not None
        assert int(announced.group(1)) > 0
    finally:
        _teardown(proc)


def test_closing_stdin_shuts_the_sidecar_down_cleanly(tmp_path: Path) -> None:
    proc = _spawn(tmp_path)
    try:
        _send(proc, {"id": "r1", "method": "debug.echo", "params": {"value": 1}})
        _read_reply(proc)

        assert proc.stdin is not None
        proc.stdin.close()

        assert proc.wait(timeout=30) == 0
        assert proc.stderr is not None
        deadline = time.monotonic() + 5.0
        chunks: list[bytes] = []
        while time.monotonic() < deadline:
            chunk = proc.stderr.read1(4096) if hasattr(proc.stderr, "read1") else proc.stderr.read(4096)
            if not chunk:
                break
            chunks.append(chunk)
        stderr = b"".join(chunks).decode("utf-8", "replace")
        assert "stdin closed" in stderr, f"missing banner; stderr was: {stderr!r}"
    finally:
        _teardown(proc)


def test_sigterm_shuts_the_sidecar_down_without_losing_the_store(tmp_path: Path) -> None:
    proc = _spawn(tmp_path)
    try:
        _send(proc, {"id": "r1", "method": "meeting.start", "params": {"title": "standup"}})
        reply = _read_reply(proc)
        meeting_id = reply["result"]["meeting_id"]

        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=30)
        assert proc.returncode is not None and proc.returncode != 0

        assert proc.stderr is not None
        assert "shutdown signal" in proc.stderr.read().decode("utf-8", "replace")
    finally:
        _teardown(proc)

    revived = _spawn(tmp_path)
    try:
        _send(revived, {"id": "r2", "method": "meeting.get", "params": {"meeting_id": meeting_id}})
        reply = _read_reply(revived)

        assert reply["result"]["meeting"]["id"] == meeting_id
    finally:
        _teardown(revived)


def test_a_killed_sidecar_reports_a_nonzero_exit_status(tmp_path: Path) -> None:
    proc = _spawn(tmp_path)
    try:
        _send(proc, {"id": "r1", "method": "debug.echo", "params": {"value": 1}})
        _read_reply(proc)

        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=30)

        assert proc.returncode != 0
    finally:
        _teardown(proc)
