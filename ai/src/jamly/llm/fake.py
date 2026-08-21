from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from .base import ChatMessage, ChatModelABC


class FakeChatModel(ChatModelABC):
    def __init__(
        self,
        tokens: tuple[str, ...] = ("hello", "world"),
        *,
        provider_id: str = "fake",
        model_name: str = "fake-model",
        delay_ms: int = 0,
        fail_with: str | None = None,
    ) -> None:
        self._tokens = tokens
        self.provider_id = provider_id
        self.model_name = model_name
        self._delay_ms = delay_ms
        self._fail_with = fail_with
        self.calls: list[tuple[ChatMessage, ...]] = []
        self.loads = 0

    def ensure_loaded(self) -> None:
        self.loads += 1

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        self.ensure_loaded()
        self.calls.append(tuple(messages))
        for index, token in enumerate(self._tokens):
            if self._fail_with is not None and index == len(self._tokens) // 2:
                raise RuntimeError(self._fail_with)
            if self._delay_ms > 0:
                await asyncio.sleep(self._delay_ms / 1000)
            yield token

    def invoke(self, messages: Sequence[ChatMessage]) -> str:
        self.calls.append(tuple(messages))
        return " ".join(self._tokens)

    def __repr__(self) -> str:
        return f"FakeChatModel(provider={self.provider_id!r}, model={self.model_name!r})"
