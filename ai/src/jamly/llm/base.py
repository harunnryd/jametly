from __future__ import annotations

import abc
from collections.abc import AsyncIterator, Sequence
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ProviderKind(StrEnum):
    AI = "ai"
    STT = "stt"


class ProviderInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    kind: ProviderKind
    default_model: str = Field(min_length=1)
    configurable: bool = True


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(min_length=1)
    content: str = Field(min_length=0)


@runtime_checkable
class ChatModel(Protocol):
    provider_id: str
    model_name: str

    def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]: ...

    def invoke(self, messages: Sequence[ChatMessage]) -> str: ...


class ChatModelABC(abc.ABC):
    provider_id: str
    model_name: str

    @abc.abstractmethod
    def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]: ...

    @abc.abstractmethod
    def invoke(self, messages: Sequence[ChatMessage]) -> str: ...


class _OllamaChatModel(ChatModelABC):
    def __init__(self, model_name: str) -> None:
        self.provider_id = "ollama"
        self.model_name = model_name

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        joined = " ".join(message.content for message in messages)
        for token in joined.split():
            yield token

    def invoke(self, messages: Sequence[ChatMessage]) -> str:
        return " ".join(message.content for message in messages)

    def __repr__(self) -> str:
        return f"OllamaChatModel(provider={self.provider_id!r}, model={self.model_name!r})"


class ProviderRegistry:
    _BUILTIN_AI: dict[str, tuple[str, type[ChatModelABC]]] = {
        "ollama": ("qwen2.5:7b-instruct", _OllamaChatModel),
    }

    _BUILTIN_STT: dict[str, tuple[str, type[ChatModelABC]]] = {
        "faster-whisper": ("small", _OllamaChatModel),
    }

    def __init__(
        self,
        *,
        providers: dict[str, tuple[str, type[ChatModelABC]]] | None = None,
        stt: dict[str, tuple[str, type[ChatModelABC]]] | None = None,
    ) -> None:
        self._ai = dict(self._BUILTIN_AI)
        self._stt = dict(self._BUILTIN_STT)
        if providers is not None:
            self._ai.update(providers)
        if stt is not None:
            self._stt.update(stt)

    def list(self, kind: str | ProviderKind | None = None) -> list[ProviderInfo]:
        if kind is None:
            ai = [self._info(pid, ProviderKind.AI) for pid in self._ai]
            stt = [self._info(pid, ProviderKind.STT) for pid in self._stt]
            return ai + stt
        try:
            resolved = ProviderKind(kind)
        except ValueError:
            return []
        if resolved is ProviderKind.AI:
            return [self._info(pid, ProviderKind.AI) for pid in self._ai]
        return [self._info(pid, ProviderKind.STT) for pid in self._stt]

    def _info(self, provider_id: str, kind: ProviderKind) -> ProviderInfo:
        default_model, _ = (self._ai if kind is ProviderKind.AI else self._stt)[provider_id]
        return ProviderInfo(
            id=provider_id,
            kind=kind,
            default_model=default_model,
        )

    def build(self, provider_id: str, *, model_name: str = "") -> ChatModel:
        for table in (self._ai, self._stt):
            entry = table.get(provider_id)
            if entry is not None:
                if not model_name.strip():
                    raise ValueError("model name must be a non-empty string")
                default, factory = entry
                return factory(model_name or default)
        raise ValueError(f"unknown provider: {provider_id!r}")


def build_chat_model(provider_id: str, *, model_name: str) -> ChatModel:
    return ProviderRegistry().build(provider_id, model_name=model_name)
