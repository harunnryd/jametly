from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SIDECAR_HOME = REPO_ROOT / ".tmp" / "jametly-meeting-session-tests"


@pytest.fixture
def fresh_home() -> Path:
    if SIDECAR_HOME.exists():
        shutil.rmtree(SIDECAR_HOME)
    SIDECAR_HOME.mkdir(parents=True)
    return SIDECAR_HOME


@pytest.fixture
def sidecar(fresh_home: Path) -> subprocess.Popen:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("`uv` not on PATH; install https://docs.astral.sh/uv/")
    env = {
        **__import__("os").environ,
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


def test_meeting_start_stop_list_round_trip(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "s1", "method": "meeting.start", "params": {"title": "Planning"}})
    start_reply, = _read_lines(sidecar, 1, timeout=15.0)
    assert "error" not in start_reply
    meeting_id = start_reply["result"]["meeting_id"]

    _send(sidecar, {"id": "s2", "method": "meeting.list", "params": {"limit": 5}})
    list_reply, = _read_lines(sidecar, 1, timeout=15.0)
    assert "error" not in list_reply
    assert any(m["id"] == meeting_id for m in list_reply["result"]["meetings"])

    _send(sidecar, {"id": "s3", "method": "meeting.stop", "params": {"meeting_id": meeting_id}})
    ended_event, stop_reply = _read_lines(sidecar, 2, timeout=15.0)
    assert ended_event["method"] == "meeting.ended"
    assert ended_event["params"]["meeting_id"] == meeting_id
    assert stop_reply == {"id": "s3", "result": {"already_ended": False}}


def test_meeting_get_returns_meeting_and_utterances(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "g1", "method": "meeting.start", "params": {"title": "Standup"}})
    start, = _read_lines(sidecar, 1, timeout=15.0)
    meeting_id = start["result"]["meeting_id"]

    _send(sidecar, {"id": "g2", "method": "meeting.get", "params": {"meeting_id": meeting_id}})
    reply, = _read_lines(sidecar, 1, timeout=15.0)
    assert "error" not in reply
    assert reply["result"]["meeting"]["id"] == meeting_id


def test_meeting_stop_emits_meeting_ended_exactly_once_on_a_double_stop(
    sidecar: subprocess.Popen,
) -> None:
    _send(sidecar, {"id": "d1", "method": "meeting.start", "params": {}})
    start, = _read_lines(sidecar, 1, timeout=15.0)
    meeting_id = start["result"]["meeting_id"]

    _send(sidecar, {"id": "d2", "method": "meeting.stop", "params": {"meeting_id": meeting_id}})
    _send(sidecar, {"id": "d3", "method": "meeting.stop", "params": {"meeting_id": meeting_id}})

    lines = _read_lines(sidecar, 3, timeout=15.0)

    events = [line for line in lines if line.get("method") == "meeting.ended"]
    replies = [line for line in lines if "result" in line]

    assert len(events) == 1
    assert events[0]["params"]["meeting_id"] == meeting_id
    by_id = {reply["id"]: reply["result"]["already_ended"] for reply in replies}
    assert by_id == {"d2": False, "d3": True}


def test_meeting_start_rejects_an_active_session(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "a1", "method": "meeting.start", "params": {}})
    first, = _read_lines(sidecar, 1, timeout=15.0)
    assert "error" not in first

    _send(sidecar, {"id": "a2", "method": "meeting.start", "params": {}})
    second, = _read_lines(sidecar, 1, timeout=15.0)
    assert "error" in second
    assert second["error"]["code"] == "INVALID_REQUEST"


def test_meeting_get_unknown_id_returns_meeting_not_found(sidecar: subprocess.Popen) -> None:
    _send(sidecar, {"id": "u1", "method": "meeting.get", "params": {"meeting_id": "missing"}})
    reply, = _read_lines(sidecar, 1, timeout=15.0)
    assert reply["error"]["code"] == "MEETING_NOT_FOUND"


def test_cold_start_writes_a_recovery_checkpoint_for_an_orphan(
    fresh_home: Path,
) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("`uv` not on PATH; install https://docs.astral.sh/uv/")

    env = {**__import__("os").environ, "JAMETLY_HOME": str(fresh_home)}
    db_path = fresh_home / ".config" / "jametly" / "jametly.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    import sqlite3

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
        INSERT INTO meetings(id, title) VALUES ('orphan-1', 'Crashed');
        PRAGMA user_version = 2;
        """
    )
    raw.commit()
    raw.close()

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
        proc.stdin.close()
        proc.wait(timeout=15)
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)

    reopened = sqlite3.connect(db_path)
    row = reopened.execute(
        "SELECT payload FROM checkpoints WHERE thread_id = 'orphan-1'"
    ).fetchone()
    meeting_row = reopened.execute(
        "SELECT ended_at FROM meetings WHERE id = 'orphan-1'"
    ).fetchone()
    reopened.close()

    assert row is not None
    assert "recovered_on_cold_start" in row[0]
    assert meeting_row[0] is None
