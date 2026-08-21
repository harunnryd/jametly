from __future__ import annotations

from enum import StrEnum

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
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


ChatModel = BaseChatModel


class ProviderRegistry:
    _BUILTIN_AI: dict[str, str] = {
        "ollama": "qwen2.5:7b-instruct",
    }

    _BUILTIN_STT: dict[str, str] = {
        "faster-whisper": "small",
    }

    def __init__(
        self,
        *,
        providers: dict[str, str] | None = None,
        stt: dict[str, str] | None = None,
    ) -> None:
        self._ai = dict(self._BUILTIN_AI)
        self._stt = dict(self._BUILTIN_STT)
        if providers is not None:
            self._ai.update(providers)
        if stt is not None:
            self._stt.update(stt)

    def list(self, kind: str | ProviderKind | None = None) -> list[ProviderInfo]:
        if kind is None:
            return self._list_kind(ProviderKind.AI) + self._list_kind(ProviderKind.STT)
        try:
            resolved = ProviderKind(kind)
        except ValueError:
            return []
        return self._list_kind(resolved)

    def _list_kind(self, kind: ProviderKind) -> list[ProviderInfo]:
        table = self._ai if kind is ProviderKind.AI else self._stt
        return [
            ProviderInfo(
                id=provider_id,
                kind=kind,
                default_model=default_model,
            )
            for provider_id, default_model in table.items()
        ]

    def build(self, provider_id: str, *, model_name: str = "") -> BaseChatModel:
        if provider_id not in self._ai:
            raise ValueError(f"unknown provider: {provider_id!r}")
        if not model_name.strip():
            raise ValueError("model name must be a non-empty string")
        return build_chat_model(provider_id, model_name=model_name)


def build_chat_model(provider_id: str, *, model_name: str) -> BaseChatModel:
    if provider_id not in ProviderRegistry()._ai:
        raise ValueError(f"unknown provider: {provider_id!r}")
    if not model_name.strip():
        raise ValueError("model name must be a non-empty string")
    return init_chat_model(model=model_name, model_provider=provider_id)