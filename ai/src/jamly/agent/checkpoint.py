from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..db import LocalStore, StoreError
from .state import AskState


class SessionsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessions: list[AskState] = Field(default_factory=list)


def _load_sessions(store: LocalStore, meeting_id: str) -> dict[str, AskState]:
    try:
        payload = store.load_checkpoint(meeting_id, SessionsPayload)
    except StoreError:
        return {}
    except ValidationError:
        return {}
    return {state.thread_id: state for state in payload.sessions}


def _save_sessions(store: LocalStore, meeting_id: str, sessions: dict[str, AskState]) -> None:
    payload = SessionsPayload(sessions=list(sessions.values()))
    store.save_checkpoint(meeting_id, payload)


def load_ask_state(store: LocalStore, meeting_id: str, thread_id: str) -> AskState | None:
    return _load_sessions(store, meeting_id).get(thread_id)


def save_ask_state(store: LocalStore, state: AskState) -> None:
    sessions = _load_sessions(store, state.meeting_id)
    sessions[state.thread_id] = state
    _save_sessions(store, state.meeting_id, sessions)
