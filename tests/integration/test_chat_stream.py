from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import time
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fresh_home(tmp_path: Path) -> Path:
    home = tmp_path / "jametly-home"
    home.mkdir(parents=True)
    return home


@pytest.fixture
def sidecar(fresh_home: Path) -> Iterator[subprocess.Popen]:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("`uv` not on PATH; install https://docs.astral.sh/uv/")
    env = {
        **os.environ,
        "JAMETLY_HOME": str(fresh_home),
        "PYTHONPATH": str(REPO_ROOT / "ai" / "src"),
    }
    proc = subprocess.Popen(
        [uv, "run", "--project", str(REPO_ROOT / "ai"), "python", "-m", "jamly"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
        start_new_session=True,
        env=env,
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
        for handle in (proc.stdin, proc.stdout, proc.stderr):
            if handle is not None:
                with contextlib.suppress(Exception):
                    handle.close()


def _send(proc: subprocess.Popen, payload: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
    proc.stdin.flush()


def _read_n(proc: subprocess.Popen, count: int, timeout: float = 25.0) -> list[dict]:
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


def test_providers_list_round_trips_through_the_live_bridge(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "p1", "method": "providers.list", "params": {}})
    reply, = _read_n(sidecar, 1, timeout=15.0)

    assert "error" not in reply
    providers = {provider["id"] for provider in reply["result"]["providers"]}
    assert {"ollama", "faster-whisper"} <= providers


def test_providers_list_filters_by_kind(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "p2", "method": "providers.list", "params": {"kind": "stt"}})
    reply, = _read_n(sidecar, 1, timeout=15.0)

    assert "error" not in reply
    assert {provider["id"] for provider in reply["result"]["providers"]} == {"faster-whisper"}


def test_chat_stream_emits_token_state_done_with_correlation_id(
    sidecar: subprocess.Popen,
) -> None:
    _send(
        sidecar,
        {
            "id": "cs1",
            "method": "chat.stream",
            "params": {
                "messages": [{"role": "user", "content": "hello world"}],
                "provider_id": "ollama",
                "model": "qwen2.5:7b-instruct",
                "thread_id": "th-it-1",
                "deadline_s": 5,
            },
        },
    )

    lines = _read_n(sidecar, 6, timeout=15.0)
    reply = lines[-1]
    events = lines[:-1]

    assert "error" not in reply
    assert reply["result"] == {"thread_id": "th-it-1", "model": "qwen2.5:7b-instruct", "tokens": 2}

    kinds = [event["params"].get("kind") for event in events]
    assert kinds[0] == "chat.state"
    assert "chat.token" in kinds
    assert kinds[-2:] == ["chat.state", "chat.done"]

    token_events = [event for event in events if event["params"].get("kind") == "chat.token"]
    assert [event["params"]["data"] for event in token_events] == ["hello", "world"]
    for event in events:
        assert event["params"]["correlation_id"] == "cs1"
        assert event["params"].get("thread_id") == "th-it-1"


def test_providers_set_selected_persists_across_a_fresh_sidecar(
    fresh_home: Path, sidecar: subprocess.Popen
) -> None:
    _send(
        sidecar,
        {
            "id": "ps1",
            "method": "providers.set_selected",
            "params": {"kind": "stt", "provider_id": "faster-whisper"},
        },
    )
    reply, = _read_n(sidecar, 1, timeout=15.0)

    assert "error" not in reply
    assert reply["result"] == {"kind": "stt", "provider_id": "faster-whisper"}

    config_path = fresh_home / ".config" / "jametly" / "config.toml"
    persisted = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["stt_provider"] == "faster-whisper"


def test_chat_stream_with_unknown_provider_returns_provider_unavailable(
    sidecar: subprocess.Popen,
) -> None:
    _send(
        sidecar,
        {
            "id": "er1",
            "method": "chat.stream",
            "params": {
                "messages": [{"role": "user", "content": "hello"}],
                "provider_id": "made-up",
                "model": "x",
            },
        },
    )
    reply, = _read_n(sidecar, 1, timeout=15.0)

    assert reply["error"]["code"] == "PROVIDER_UNAVAILABLE"
