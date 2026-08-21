from __future__ import annotations

import contextlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
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
def seeded_home(fresh_home: Path) -> tuple[Path, str]:
    """Pre-create a SQLite DB with v2 schema + a single seeded meeting/utterances."""
    db_path = fresh_home / ".config" / "jametly" / "jametly.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE meetings (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ended_at TEXT
        );
        CREATE TABLE utterances (
            id TEXT PRIMARY KEY,
            meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
            speaker TEXT NOT NULL,
            text TEXT NOT NULL,
            start_ms INTEGER NOT NULL,
            end_ms INTEGER NOT NULL,
            confidence REAL NOT NULL,
            segment_id TEXT NOT NULL DEFAULT ''
        );
        CREATE VIRTUAL TABLE utterances_fts USING fts5(
            text,
            content='utterances',
            content_rowid='rowid'
        );
        CREATE TRIGGER utterances_ai AFTER INSERT ON utterances BEGIN
            INSERT INTO utterances_fts(rowid, text) VALUES (new.rowid, new.text);
        END;
        CREATE TRIGGER utterances_ad AFTER DELETE ON utterances BEGIN
            INSERT INTO utterances_fts(utterances_fts, rowid, text)
            VALUES ('delete', old.rowid, old.text);
        END;
        CREATE TRIGGER utterances_au AFTER UPDATE OF text ON utterances BEGIN
            INSERT INTO utterances_fts(utterances_fts, rowid, text)
            VALUES ('delete', old.rowid, old.text);
            INSERT INTO utterances_fts(rowid, text) VALUES (new.rowid, new.text);
        END;
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE action_items (
            id TEXT PRIMARY KEY,
            meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
            body TEXT NOT NULL,
            owner TEXT,
            completed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE checkpoints (
            thread_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO meetings(id, title) VALUES ('seeded-meeting-1', 'Seeded');
        INSERT INTO utterances(id, meeting_id, speaker, text, start_ms, end_ms, confidence, segment_id)
            VALUES ('utt-1', 'seeded-meeting-1', 'A', 'we agreed on Friday deadline', 0, 500, 0.9, 'seg-1');
        INSERT INTO utterances(id, meeting_id, speaker, text, start_ms, end_ms, confidence, segment_id)
            VALUES ('utt-2', 'seeded-meeting-1', 'B', 'sounds good thank you', 600, 1200, 0.9, 'seg-1');
        PRAGMA user_version = 2;
        """
    )
    raw.commit()
    raw.close()
    return fresh_home, "seeded-meeting-1"


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
            pytest.fail(
                f"sidecar closed stdout after {len(out)}/{count} lines. stderr:\n{tail}"
            )
        out.append(json.loads(raw.decode("utf-8").strip()))
    return out


def _read_reply(proc: subprocess.Popen, timeout: float = 15.0) -> tuple[dict, list[dict]]:
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    events: list[dict] = []
    while True:
        if time.monotonic() >= deadline:
            pytest.fail(f"timed out waiting for reply; got events={events}")
        raw = proc.stdout.readline()
        if not raw:
            tail = proc.stderr.read1(4096).decode("utf-8", "replace") if proc.stderr else ""
            pytest.fail(
                f"sidecar closed stdout after {len(events)} events. stderr:\n{tail}"
            )
        line = json.loads(raw.decode("utf-8").strip())
        if "result" in line or "error" in line:
            return line, events
        events.append(line)


def test_ask_stream_round_trip_with_seeded_meeting(
    seeded_home: tuple[Path, str],
) -> None:
    home, meeting_id = seeded_home
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("`uv` not on PATH; install https://docs.astral.sh/uv/")
    env = {**os.environ, "JAMETLY_HOME": str(home), "PYTHONPATH": str(REPO_ROOT / "ai" / "src")}
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
        _send(
            proc,
            {
                "id": "ask1",
                "method": "ask.stream",
                "params": {
                    "meeting_id": meeting_id,
                    "question": "what was decided?",
                    "thread_id": "th-it-1",
                    "deadline_s": 10.0,
                    "provider_id": "ollama",
                    "model": "qwen2.5:7b-instruct",
                },
            },
        )
        reply, events = _read_reply(proc, timeout=15.0)
        assert "error" not in reply
        assert reply["result"]["thread_id"] == "th-it-1"
        assert reply["result"]["meeting_id"] == meeting_id
        assert isinstance(reply["result"].get("answer"), str)
        assert isinstance(reply["result"].get("citations"), list)
        assert len(reply["result"]["citations"]) >= 2

        kinds = [event["params"].get("kind") for event in events]
        assert kinds[0] == "ask.state"
        assert "ask.token" in kinds
        assert "ask.citation" in kinds
        assert kinds[-2:] == ["ask.state", "ask.done"]

        token_events = [event for event in events if event["params"].get("kind") == "ask.token"]
        assert len(token_events) >= 1
        for token_event in token_events:
            assert token_event["params"]["correlation_id"] == "ask1"
            assert token_event["params"]["thread_id"] == "th-it-1"

        citation_events = [
            event for event in events if event["params"].get("kind") == "ask.citation"
        ]
        assert {event["params"]["utterance_id"] for event in citation_events} >= {
            "utt-1",
            "utt-2",
        }
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


def test_ask_stream_unknown_meeting_returns_meeting_not_found(sidecar: subprocess.Popen) -> None:
    _send(
        sidecar,
        {
            "id": "ask2",
            "method": "ask.stream",
            "params": {
                "meeting_id": "missing",
                "question": "anything",
                "thread_id": "th-it-2",
                "deadline_s": 5.0,
            },
        },
    )
    reply, = _read_n(sidecar, 1, timeout=10.0)
    assert reply["error"]["code"] == "MEETING_NOT_FOUND"


def test_ask_stream_tool_path_emits_call_and_result(
    seeded_home: tuple[Path, str],
) -> None:
    home, _ = seeded_home
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("`uv` not on PATH; install https://docs.astral.sh/uv/")
    env = {**os.environ, "JAMETLY_HOME": str(home), "PYTHONPATH": str(REPO_ROOT / "ai" / "src")}
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
        _send(
            proc,
            {
                "id": "ask3",
                "method": "ask.stream",
                "params": {
                    "tool": "search_history",
                    "tool_args": {"query": "deadline", "limit": 3},
                    "thread_id": "th-it-3",
                },
            },
        )
        lines = _read_n(proc, 4, timeout=10.0)
        reply = lines[-1]
        events = lines[:-1]
        kinds = [event["params"].get("kind") for event in events]
        assert kinds == ["ask.tool_call", "ask.tool_result", "ask.done"]
        assert reply["result"]["tool"] == "search_history"
        assert len(reply["result"]["result"]["results"]) >= 1
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


def test_ask_cancel_unknown_thread_returns_zero(sidecar: subprocess.Popen) -> None:
    _send(
        sidecar,
        {
            "id": "ask4",
            "method": "ask.cancel",
            "params": {"thread_id": "nope"},
        },
    )
    reply, = _read_n(sidecar, 1, timeout=10.0)
    assert "error" not in reply
    assert reply["result"] == {"thread_id": "nope", "cancelled": 0}


def test_ask_stream_checkpoint_survives_sidecar_restart(
    seeded_home: tuple[Path, str],
) -> None:
    home, meeting_id = seeded_home
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("`uv` not on PATH; install https://docs.astral.sh/uv/")
    env = {**os.environ, "JAMETLY_HOME": str(home), "PYTHONPATH": str(REPO_ROOT / "ai" / "src")}

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
        _send(
            proc,
            {
                "id": "ask5a",
                "method": "ask.stream",
                "params": {
                    "meeting_id": meeting_id,
                    "question": "what is the deadline?",
                    "thread_id": "th-it-5",
                    "deadline_s": 10.0,
                    "provider_id": "ollama",
                    "model": "qwen2.5:7b-instruct",
                },
            },
        )
        reply, _events = _read_reply(proc, timeout=15.0)
        assert "error" not in reply
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
        db_path = home / ".config" / "jametly" / "jametly.sqlite"
        raw = sqlite3.connect(db_path)
        row = raw.execute(
            "SELECT payload FROM checkpoints WHERE thread_id = ?", (meeting_id,)
        ).fetchone()
        raw.close()
        assert row is not None
        payload = row[0]
        assert "th-it-5" in payload
        assert meeting_id in payload
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
