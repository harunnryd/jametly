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


def _read_lines(proc: subprocess.Popen, count: int, timeout: float = 20.0) -> list[dict]:
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


def test_debug_stream_emits_events_before_the_reply(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "r1", "method": "debug.stream", "params": {"count": 2}})

    lines = _read_lines(sidecar, 4)
    events, reply = lines[:3], lines[3]

    assert all("id" not in e for e in events), f"events must be uncorrelated: {events}"
    assert [e["method"] for e in events] == ["stream.event"] * 3
    assert [e["params"]["kind"] for e in events] == ["token", "token", "done"]
    assert {e["params"]["correlation_id"] for e in events} == {"r1"}
    assert reply == {"id": "r1", "result": {"count": 2}}


def test_events_do_not_break_reply_correlation(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "r1", "method": "debug.stream", "params": {"count": 1}})
    _send(sidecar, {"id": "r2", "method": "echo", "params": {"x": "hi"}})

    lines = _read_lines(sidecar, 4)

    assert [line.get("method") for line in lines[:2]] == ["stream.event"] * 2
    assert lines[2] == {"id": "r1", "result": {"count": 1}}
    assert lines[3] == {"id": "r2", "result": {"x": "hi"}}


def test_debug_stream_with_zero_count_emits_only_done(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "r1", "method": "debug.stream", "params": {"count": 0}})

    lines = _read_lines(sidecar, 2)

    assert lines[0]["params"]["kind"] == "done"
    assert lines[1] == {"id": "r1", "result": {"count": 0}}


def test_bad_count_replies_with_error_and_no_events(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "r1", "method": "debug.stream", "params": {"count": -3}})

    (line,) = _read_lines(sidecar, 1)

    assert line["id"] == "r1"
    assert line["error"]["code"] == "INVALID_REQUEST"
