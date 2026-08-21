from __future__ import annotations

import socket

import pytest

from tests.support import ollama_reachable


class _NoopSocket:
    def __enter__(self) -> _NoopSocket:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def test_ollama_reachable_returns_true_when_socket_connects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda host_port, timeout: _NoopSocket(),
    )
    assert ollama_reachable("http://localhost:11434") is True


def test_ollama_reachable_returns_false_when_socket_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> _NoopSocket:
        raise OSError("Connection refused")

    monkeypatch.setattr(socket, "create_connection", _raise)
    assert ollama_reachable("http://localhost:11434") is False


def test_ollama_reachable_honors_ollama_base_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _capture(host_port: object, timeout: object) -> _NoopSocket:
        captured["host_port"] = host_port
        return _NoopSocket()

    monkeypatch.setattr(socket, "create_connection", _capture)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://gpu-host.local:9999")
    assert ollama_reachable() is True
    assert captured["host_port"] == ("gpu-host.local", 9999)


def test_ollama_reachable_defaults_to_localhost_11434(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    def _capture(host_port: object, timeout: object) -> _NoopSocket:
        captured["host_port"] = host_port
        return _NoopSocket()

    monkeypatch.setattr(socket, "create_connection", _capture)
    assert ollama_reachable() is True
    assert captured["host_port"] == ("localhost", 11434)
