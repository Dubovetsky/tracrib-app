from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def optional_int_from_env(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    parsed = int(value)
    return parsed or None


def optional_secret_from_file(path: str | None) -> str | None:
    if not path:
        return None
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


DEFAULT_ASR_GLOSSARY = (
    "Русская деловая встреча с IT и process terminology. "
    "Пиши английские IT и Agile аббревиатуры латиницей и верхним регистром: "
    "EADR, ADR, IDR, DR, RFC, Jira, AirPoint, GSM, CM, TMH, QA, API, UI, UX, MVP, CI/CD, "
    "PR, DoD, DoR, WIP, OKR, KPI, SLA, SLO, SLI."
)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("TRANSCRIB_APP_DATA_DIR", "backend/data"))
    whisper_model: str = os.getenv("WHISPER_MODEL", "large-v3-turbo")
    whisper_accurate_model: str = os.getenv(
        "WHISPER_ACCURATE_MODEL",
        "backend/data/huggingface/hub/models--Systran--faster-whisper-large-v3-local",
    )
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cuda")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
    whisper_fallback_compute_type: str = os.getenv("WHISPER_FALLBACK_COMPUTE_TYPE", "int8_float16")
    whisper_initial_prompt: str = os.getenv("WHISPER_INITIAL_PROMPT", DEFAULT_ASR_GLOSSARY)
    whisper_hotwords: str = os.getenv("WHISPER_HOTWORDS", DEFAULT_ASR_GLOSSARY)
    asr_quality: str = os.getenv("ASR_QUALITY", "balanced")
    audio_profile: str = os.getenv("AUDIO_PROFILE", "speech")
    language: str = "ru"
    diarization_enabled: bool = os.getenv("DIARIZATION_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
    diarization_model: str = os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1")
    diarization_device: str = os.getenv("DIARIZATION_DEVICE", os.getenv("WHISPER_DEVICE", "cuda"))
    diarization_num_speakers: int | None = optional_int_from_env("DIARIZATION_NUM_SPEAKERS")
    diarization_min_speakers: int | None = optional_int_from_env("DIARIZATION_MIN_SPEAKERS")
    diarization_max_speakers: int | None = optional_int_from_env("DIARIZATION_MAX_SPEAKERS")
    diarization_auth_token: str | None = (
        os.getenv("HF_TOKEN")
        or os.getenv("HUGGINGFACE_TOKEN")
        or optional_secret_from_file(os.getenv("HF_TOKEN_FILE", "backend/data/secrets/hf_token.txt"))
    )
    preserve_asr_words: bool = os.getenv("PRESERVE_ASR_WORDS", "1").strip().lower() in {"1", "true", "yes", "on"}
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
