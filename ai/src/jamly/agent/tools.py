from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from ..db import LocalStore


class ToolError(Exception):
    name: str = ""


class UnknownToolError(ToolError):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class ToolMutationError(ToolError):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    mutates: bool = False


class SearchHistoryInput(BaseModel):
    model_config = {"extra": "forbid"}

    query: str = Field(default="", min_length=0)
    limit: int = Field(default=5, ge=1, le=100)


_search_history_store: LocalStore | None = None


def _resolve_store(store: LocalStore | None) -> LocalStore | None:
    if store is not None:
        return store
    return _search_history_store


@tool("search_history", args_schema=SearchHistoryInput)
def search_history(query: str, limit: int = 5, *, store: LocalStore | None = None) -> dict:
    """Search saved meeting transcripts via FTS5 ranking (read-only)."""
    rows: list[dict] = []
    resolved = _resolve_store(store)
    if resolved is not None and query:
        rows = resolved.search(query, limit=limit)
    return {"results": rows}


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "search_history": ToolSpec(
        name="search_history",
        description=search_history.description,
        mutates=False,
    ),
}


def invoke_tool(name: str, args: dict | None, *, store: LocalStore | None) -> dict:
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        raise UnknownToolError(name)
    if spec.mutates:
        raise ToolMutationError(name)
    if not isinstance(args, dict):
        raise ValueError("tool args must be a dict")
    if name == "search_history":
        return _invoke_search_history(args, store=store)
    raise UnknownToolError(name)


def _invoke_search_history(args: dict, *, store: LocalStore | None) -> dict:
    query = args.get("query", "")
    if not isinstance(query, str):
        raise ValueError("search_history query must be a string")
    limit_raw = args.get("limit", 5)
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("search_history limit must be an integer") from exc
    if store is None:
        return {"results": []}
    rows = store.search(query, limit=limit)
    return {"results": rows}
