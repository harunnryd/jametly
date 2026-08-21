from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConfigPaths(BaseModel):
    model_config = ConfigDict(frozen=True)

    config_file: Path
    transcripts_dir: Path
    blobs_dir: Path

    @classmethod
    def from_home(cls, home: Path) -> ConfigPaths:
        root = home / ".config" / "jametly"
        return cls(
            config_file=root / "config.toml",
            transcripts_dir=root / "transcripts",
            blobs_dir=root / "_blobs",
        )


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_provider: str = Field(default="ollama", min_length=1)
    ai_model: str = Field(default="qwen2.5:7b-instruct", min_length=1)
    stt_provider: str = Field(default="faster-whisper", min_length=1)
    stt_model: str = Field(default="small", min_length=1)
    stt_model_dir: Path | None = Field(default=None)
    stt_device: str = Field(default="cpu", pattern="^(cpu|cuda|auto)$")
    stt_compute_type: str = Field(default="int8", min_length=1)
    audio_kind: str = Field(default="loopback", pattern="^(mic|loopback)$")
    language: str | None = Field(default=None, min_length=2, max_length=16)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, Path):
        return json.dumps(str(value))
    if isinstance(value, str):
        return json.dumps(value)
    if value is None:
        return '""'
    raise TypeError(f"unsupported config value: {value!r}")


def load_config(path: Path) -> AppConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return AppConfig.model_validate(raw)


def save_config(path: Path, config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for field_name in type(config).model_fields:
        value = getattr(config, field_name)
        if value is None:
            continue
        lines.append(f"{field_name} = {_toml_value(value)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
