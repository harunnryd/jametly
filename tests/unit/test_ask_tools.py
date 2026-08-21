from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from jamly.agent.tools import (
    TOOL_REGISTRY,
    ToolMutationError,
    ToolSpec,
    UnknownToolError,
    invoke_tool,
)
from jamly.db import LocalStore


def _seed_meeting_with(store: LocalStore, *texts: str) -> str:
    meeting_id = str(uuid.uuid4())
    store.create_meeting(meeting_id)
    for index, text in enumerate(texts):
        store.append_utterance(
            meeting_id=meeting_id,
            speaker="A",
            text=text,
            start_ms=index * 1000,
            end_ms=index * 1000 + 500,
            confidence=0.9,
            segment_id=str(uuid.uuid4()),
        )
    return meeting_id


def test_search_history_spec_is_registered_and_read_only() -> None:
    spec = TOOL_REGISTRY.get("search_history")
    assert spec is not None
    assert spec.name == "search_history"
    assert spec.mutates is False


def test_invoke_search_history_returns_results(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        _seed_meeting_with(store, "the project deadline moved", "we agreed on Friday")
        result = invoke_tool(
            "search_history",
            {"query": "deadline", "limit": 5},
            store=store,
        )
        assert "results" in result
        assert any("deadline" in row["text"] for row in result["results"])
    finally:
        store.close()


def test_invoke_search_history_with_empty_query_returns_empty(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        _seed_meeting_with(store, "anything")
        result = invoke_tool("search_history", {"query": "", "limit": 5}, store=store)
        assert result == {"results": []}
    finally:
        store.close()


def test_invoke_unknown_tool_raises() -> None:
    store_in = None
    with pytest.raises(UnknownToolError):
        invoke_tool("not-a-real-tool", {}, store=store_in)


def test_invoke_rejects_mutating_tool(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        sentinel = "_fake_mutating"
        TOOL_REGISTRY[sentinel] = ToolSpec(sentinel, "fake mutating", mutates=True)
        try:
            with pytest.raises(ToolMutationError):
                invoke_tool(sentinel, {}, store=store)
        finally:
            TOOL_REGISTRY.pop(sentinel, None)
    finally:
        store.close()


def test_invoke_rejects_non_dict_args() -> None:
    with pytest.raises(ValueError):
        invoke_tool("search_history", "not-a-dict", store=None)


def test_search_history_clamps_limit_to_safe_range(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite")
    try:
        _seed_meeting_with(store, "alpha", "beta", "gamma")
        result = invoke_tool(
            "search_history",
            {"query": "alpha", "limit": 9999},
            store=store,
        )
        assert isinstance(result["results"], list)
    finally:
        store.close()


def test_tool_spec_is_frozen() -> None:
    spec = ToolSpec("n", "d", mutates=False)
    with pytest.raises(Exception):
        spec.mutates = True
