from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_uv() -> str:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("`uv` not on PATH; install https://docs.astral.sh/uv/")
    return uv


@pytest.fixture
def sidecar() -> subprocess.Popen:
    uv = _resolve_uv()
    proc = subprocess.Popen(
        [uv, "run", "--project", str(REPO_ROOT / "ai"), "python", "-m", "jamly"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
        start_new_session=True,
    )
    try:
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _send(proc: subprocess.Popen, payload: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
    proc.stdin.flush()


def _read_lines(proc: subprocess.Popen, count: int, timeout: float = 25.0) -> list[dict]:
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    out: list[dict] = []
    while len(out) < count:
        if time.monotonic() >= deadline:
            pytest.fail(f"timed out after {len(out)}/{count} lines: {out}")
        raw = proc.stdout.readline()
        if not raw:
            tail = proc.stderr.read1(4096).decode("utf-8", "replace") if proc.stderr else ""
            pytest.fail(f"sidecar closed stdout after {len(out)}/{count} lines. stderr:\n{tail}")
        out.append(json.loads(raw.decode("utf-8").strip()))
    return out


def test_slow_request_completes_while_stdin_stays_open(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "slow", "method": "debug.sleep", "params": {"ms": 300}})

    (reply,) = _read_lines(sidecar, 1, timeout=15.0)

    assert reply == {"id": "slow", "result": {"slept_ms": 300}}


def test_fast_request_overtakes_a_slow_one(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "slow", "method": "debug.sleep", "params": {"ms": 2000}})
    _send(sidecar, {"id": "fast", "method": "echo", "params": {"x": "hi"}})

    first, second = _read_lines(sidecar, 2, timeout=20.0)

    assert first == {"id": "fast", "result": {"x": "hi"}}
    assert second == {"id": "slow", "result": {"slept_ms": 2000}}


def test_events_flow_while_a_slow_request_is_in_flight(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "slow", "method": "debug.sleep", "params": {"ms": 2000}})
    _send(sidecar, {"id": "stream", "method": "debug.stream", "params": {"count": 2}})

    lines = _read_lines(sidecar, 5, timeout=20.0)

    assert [line.get("method") for line in lines[:3]] == ["stream.event"] * 3
    assert lines[3] == {"id": "stream", "result": {"count": 2}}
    assert lines[4] == {"id": "slow", "result": {"slept_ms": 2000}}


def test_concurrent_requests_all_correlate(sidecar: subprocess.Popen) -> None:
    for index in range(10):
        _send(sidecar, {"id": f"r{index}", "method": "echo", "params": {"n": index}})

    lines = _read_lines(sidecar, 10, timeout=20.0)

    assert {line["id"]: line["result"]["n"] for line in lines} == {
        f"r{index}": index for index in range(10)
    }


def test_eof_cancels_in_flight_work_with_a_terminal_signal(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "slow", "method": "debug.sleep", "params": {"ms": 60000}})
    assert sidecar.stdin is not None
    sidecar.stdin.close()

    event, reply = _read_lines(sidecar, 2, timeout=20.0)

    assert event["method"] == "stream.event"
    assert event["params"] == {"correlation_id": "slow", "kind": "cancelled"}
    assert reply == {"id": "slow", "result": {"cancelled": True}}
