from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from tests.support import FakeProvider

OFFLINE_KEYS = ("HF_HUB_OFFLINE", "HF_HOME", "HF_HUB_DISABLE_TELEMETRY")


@pytest.fixture(autouse=True, scope="session")
def offline_model_cache(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    root = tmp_path_factory.mktemp("hf-offline")
    previous = {key: os.environ.get(key) for key in OFFLINE_KEYS}
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HOME"] = str(root)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()
