from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from jamly.llm import (
    ProviderInfo,
    ProviderKind,
    ProviderRegistry,
    build_chat_model,
)


def test_registry_lists_built_in_providers_for_each_kind() -> None:
    registry = ProviderRegistry()

    ai_providers = registry.list(kind=ProviderKind.AI)
    stt_providers = registry.list(kind=ProviderKind.STT)

    assert {provider.id for provider in ai_providers} >= {"ollama"}
    assert {provider.id for provider in stt_providers} >= {"faster-whisper"}

    for provider in ai_providers + stt_providers:
        assert isinstance(provider, ProviderInfo)
        assert provider.default_model
        assert provider.configurable is True


def test_registry_includes_only_ai_providers_by_default() -> None:
    registry = ProviderRegistry()

    listed = registry.list()

    assert {provider.id for provider in listed} == {
        provider.id
        for provider in registry.list(kind=ProviderKind.AI) + registry.list(kind=ProviderKind.STT)
    }


def test_registry_unknown_kind_returns_an_empty_list() -> None:
    registry = ProviderRegistry()

    assert registry.list(kind=ProviderKind.AI) != []
    assert registry.list(kind="unknown") == []


def test_build_chat_model_returns_langchain_base_chat_model() -> None:
    registry = ProviderRegistry()

    model = registry.build("ollama", model_name="qwen2.5:7b-instruct")

    assert isinstance(model, BaseChatModel)


def test_build_chat_model_delegates_to_init_chat_model(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_init(
        model: str | None = None,
        *,
        model_provider: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        captured["model"] = model
        captured["model_provider"] = model_provider
        captured.update(kwargs)
        return init_chat_model("ollama:gpt-oss:20b", model_provider="ollama")

    monkeypatch.setattr("jamly.llm.base.init_chat_model", fake_init)

    model = build_chat_model("ollama", model_name="qwen2.5:7b-instruct")

    assert isinstance(model, BaseChatModel)
    assert captured.get("model_provider") == "ollama"
    assert captured.get("model") == "qwen2.5:7b-instruct"


def test_build_chat_model_rejects_unknown_provider() -> None:
    registry = ProviderRegistry()

    with pytest.raises(ValueError, match="unknown provider"):
        registry.build("not-a-real-provider")


def test_build_chat_model_rejects_empty_model_name() -> None:
    registry = ProviderRegistry()

    with pytest.raises(ValueError, match="model name"):
        registry.build("ollama", model_name="")


def test_module_level_factory_delegates_to_a_fresh_registry() -> None:
    model_a = build_chat_model("ollama", model_name="qwen2.5:7b-instruct")
    model_b = build_chat_model("ollama", model_name="qwen2.5:7b-instruct")

    assert isinstance(model_a, BaseChatModel)
    assert isinstance(model_b, BaseChatModel)
    assert model_a is not model_b


def test_build_chat_model_result_streams_via_langchain_astream() -> None:
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel

    model = FakeMessagesListChatModel(responses=[AIMessage(content="hello world")])

    async def collect() -> list[str]:
        out: list[str] = []
        async for chunk in model.astream([]):
            content = getattr(chunk, "content", "")
            if isinstance(content, str):
                out.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        out.append(item["text"])
        return out

    import asyncio

    chunks = asyncio.run(collect())
    assert "".join(chunks) == "hello world"