from __future__ import annotations

import subprocess
from pathlib import Path


def preprocess_audio(input_path: Path, output_path: Path, profile: str = "speech") -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_profile = normalize_audio_profile(profile)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        *audio_filter_args(normalized_profile),
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg not found in PATH. Install ffmpeg and restart backend.") from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"ffmpeg could not prepare audio: {details}") from exc
    return {"audio_profile": normalized_profile, **probe_audio(output_path)}


def normalize_audio_profile(profile: str | None) -> str:
    normalized = (profile or "speech").strip().lower()
    if normalized not in {"plain", "speech", "conservative"}:
        return "speech"
    return normalized


def audio_filter_args(profile: str) -> list[str]:
    if profile == "plain":
        return []
    if profile == "conservative":
        return ["-af", "highpass=f=70,lowpass=f=7800"]
    return ["-af", "highpass=f=80,lowpass=f=7600,loudnorm=I=-18:LRA=11:TP=-1.5"]


def probe_audio(audio_path: Path) -> dict[str, object]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=channels,sample_rate,duration:format=duration",
        "-of",
        "default=noprint_wrappers=1",
        str(audio_path),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {}

    diagnostics: dict[str, object] = {}
    for line in completed.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "sample_rate":
            diagnostics["sample_rate"] = safe_int(value)
        elif key == "channels":
            diagnostics["channels"] = safe_int(value)
        elif key == "duration":
            diagnostics["duration_seconds"] = safe_float(value)
    return diagnostics


def safe_int(value: str) -> int | None:
    try:
        return int(float(value))
    except ValueError:
        return None


def safe_float(value: str) -> float | None:
    try:
        return round(float(value), 3)
    except ValueError:
        return None
