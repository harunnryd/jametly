from __future__ import annotations

import pytest

from jamly.llm import (
    ChatModel,
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


def test_build_chat_model_returns_a_chat_model_instance() -> None:
    registry = ProviderRegistry()

    model = registry.build("ollama", model_name="qwen2.5:7b-instruct")

    assert isinstance(model, ChatModel)
    assert model.provider_id == "ollama"
    assert model.model_name == "qwen2.5:7b-instruct"


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

    assert isinstance(model_a, ChatModel)
    assert isinstance(model_b, ChatModel)
    assert model_a is not model_b


def test_chat_model_repr_surfaces_provider_and_model() -> None:
    model = build_chat_model("ollama", model_name="qwen2.5:7b-instruct")

    assert "ollama" in repr(model)
    assert "qwen2.5:7b-instruct" in repr(model)
