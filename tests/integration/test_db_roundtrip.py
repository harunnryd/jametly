from __future__ import annotations

from pathlib import Path

from jamly.db import LocalStore


def test_store_reopens_with_persisted_search_index(tmp_path: Path) -> None:
    path = tmp_path / "meeting.sqlite"
    first = LocalStore(path)
    meeting_id = first.create_meeting("meeting-1")
    first.append_utterance(meeting_id, "A", "decision recorded", 0, 100, 0.8)
    first.close()

    second = LocalStore(path)
    assert second.search("decision")[0]["meeting_id"] == meeting_id
    second.close()
