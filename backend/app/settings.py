from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def optional_int_from_env(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    parsed = int(value)
    return parsed or None


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("TRANSCRIB_APP_DATA_DIR", "backend/data"))
    whisper_model: str = os.getenv("WHISPER_MODEL", "large-v3-turbo")
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cuda")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
    whisper_fallback_compute_type: str = os.getenv("WHISPER_FALLBACK_COMPUTE_TYPE", "int8_float16")
    language: str = "ru"
    diarization_enabled: bool = os.getenv("DIARIZATION_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
    diarization_model: str = os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1")
    diarization_device: str = os.getenv("DIARIZATION_DEVICE", os.getenv("WHISPER_DEVICE", "cuda"))
    diarization_min_speakers: int | None = optional_int_from_env("DIARIZATION_MIN_SPEAKERS")
    diarization_max_speakers: int | None = optional_int_from_env("DIARIZATION_MAX_SPEAKERS")
    diarization_auth_token: str | None = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
    text_polish_provider: str = os.getenv("TEXT_POLISH_PROVIDER", "auto")
    text_polish_providers: tuple[str, ...] = tuple(
        part.strip().lower()
        for part in os.getenv("TEXT_POLISH_PROVIDERS", "").split(",")
        if part.strip()
    )
    text_polish_model: str = os.getenv("TEXT_POLISH_MODEL", "gpt-5-mini")
    text_polish_timeout_seconds: float = float(os.getenv("TEXT_POLISH_TIMEOUT_SECONDS", "90"))
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "transcrib.sqlite3"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def wav_dir(self) -> Path:
        return self.data_dir / "wav"

    @property
    def result_dir(self) -> Path:
        return self.data_dir / "results"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"


settings = Settings()
