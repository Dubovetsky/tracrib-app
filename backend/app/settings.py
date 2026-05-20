from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("TRANSCRIB_APP_DATA_DIR", "backend/data"))
    whisper_model: str = os.getenv("WHISPER_MODEL", "large-v3-turbo")
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cuda")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
    whisper_fallback_compute_type: str = os.getenv("WHISPER_FALLBACK_COMPUTE_TYPE", "int8_float16")
    language: str = "ru"
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


settings = Settings()
