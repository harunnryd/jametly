from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from jamly.config import AppConfig, ConfigPaths


def test_default_config_is_local_and_selects_local_models(tmp_path: Path) -> None:
    paths = ConfigPaths.from_home(tmp_path)
    config = AppConfig()

    assert paths.config_file == tmp_path / ".config" / "jametly" / "config.toml"
    assert paths.transcripts_dir == tmp_path / ".config" / "jametly" / "transcripts"
    assert config.ai_provider == "ollama"
    assert config.ai_model == "qwen2.5:7b-instruct"


def test_config_rejects_unknown_fields_and_secret_values() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"telemetry": True})

    with pytest.raises(ValidationError):
        AppConfig.model_validate({"openai_api_key": "secret"})


def test_config_validates_provider_and_audio_values() -> None:
    config = AppConfig.model_validate(
        {
            "ai_provider": "ollama",
            "ai_model": "local-model",
            "stt_provider": "faster-whisper",
            "audio_kind": "loopback",
            "language": "en",
        }
    )
    assert config.audio_kind == "loopback"

    with pytest.raises(ValidationError):
        AppConfig.model_validate({"audio_kind": "speaker"})


def test_config_dump_never_contains_secret_fields() -> None:
    dumped = AppConfig().model_dump()
    assert all("key" not in field and "secret" not in field for field in dumped)
