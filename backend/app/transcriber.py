from __future__ import annotations

import os
import site
import sys
import logging
from pathlib import Path
from typing import NamedTuple

from .diarization import DiarizationEngine, apply_diarization
from .exports import TranscriptSegment, TranscriptWord
from .hf_env import remove_dead_local_proxy
from .postprocess import postprocess_transcript


LOGGER = logging.getLogger("transcrib_app.backend")
_CUDA_DLL_DIRS: list[object] = []
_CUDA_DLL_DIRS_ADDED = False


class ModelLoadAttempt(NamedTuple):
    device: str
    compute_type: str
    error: str


class TranscriptionError(RuntimeError):
    pass


def _add_windows_cuda_dll_dirs() -> None:
    global _CUDA_DLL_DIRS_ADDED
    if _CUDA_DLL_DIRS_ADDED or sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return

    candidates: list[Path] = []
    site_dirs = [*site.getsitepackages(), site.getusersitepackages()]
    for site_dir in site_dirs:
        root = Path(site_dir) / "nvidia"
        candidates.extend([root / "cublas" / "bin", root / "cudnn" / "bin"])

    for candidate in candidates:
        if candidate.exists():
            _CUDA_DLL_DIRS.append(os.add_dll_directory(str(candidate)))
            os.environ["PATH"] = f"{candidate}{os.pathsep}{os.environ.get('PATH', '')}"
    _CUDA_DLL_DIRS_ADDED = True


class FasterWhisperEngine:
    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        fallback_compute_type: str,
        diarization_engine: DiarizationEngine | None = None,
        initial_prompt: str | None = None,
        hotwords: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.fallback_compute_type = fallback_compute_type
        self.diarization_engine = diarization_engine
        self.initial_prompt = initial_prompt
        self.hotwords = hotwords
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model

        _add_windows_cuda_dll_dirs()
        remove_dead_local_proxy()
        from faster_whisper import WhisperModel

        attempts = [
            ("cuda", self.compute_type),
            ("cuda", self.fallback_compute_type),
            ("cpu", "int8"),
        ]
        errors: list[ModelLoadAttempt] = []
        for device, compute_type in attempts:
            try:
                self._model = WhisperModel(
                    self.model_name,
                    device=device,
                    compute_type=compute_type,
                )
                self.device = device
                self.compute_type = compute_type
                return self._model
            except Exception as exc:
                errors.append(ModelLoadAttempt(device, compute_type, str(exc)))

        details = "; ".join(
            f"{attempt.device}/{attempt.compute_type}: {attempt.error}" for attempt in errors
        )
        raise TranscriptionError(
            "Не удалось загрузить faster-whisper. "
            "Проверены режимы: CUDA float16, CUDA int8_float16, CPU int8. "
            f"Детали: {details}"
        )

    def transcribe(self, audio_path: Path, language: str = "ru") -> tuple[str, list[TranscriptSegment]]:
        model = self._load_model()
        raw_segments, _ = model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
            beam_size=5,
            word_timestamps=True,
            condition_on_previous_text=False,
            initial_prompt=self.initial_prompt or None,
            hotwords=self.hotwords or None,
        )
        segments: list[TranscriptSegment] = []
        for segment in raw_segments:
            text = segment.text.strip()
            if not text:
                continue
            transcript_segment: TranscriptSegment = {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": text,
            }
            words = extract_segment_words(segment)
            if words:
                transcript_segment["words"] = words
            segments.append(transcript_segment)
        if not segments:
            return "", []
        if self.diarization_engine is not None:
            try:
                turns = self.diarization_engine.diarize(audio_path)
                segments = apply_diarization(segments, turns)
            except Exception:
                LOGGER.exception("Diarization failed; falling back to text-only speaker assignment.")
        return postprocess_transcript(segments, language=language)


def extract_segment_words(segment: object) -> list[TranscriptWord]:
    words = getattr(segment, "words", None) or []
    extracted: list[TranscriptWord] = []
    for word in words:
        text = str(getattr(word, "word", "")).strip()
        if not text:
            continue
        start = getattr(word, "start", None)
        end = getattr(word, "end", None)
        if start is None or end is None:
            continue
        extracted.append({"start": float(start), "end": float(end), "word": text})
    return extracted
