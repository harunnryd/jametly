"""Validated non-secret local configuration for the AI sidecar."""

from __future__ import annotations

from pathlib import Path

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
