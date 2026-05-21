from __future__ import annotations

import os
import site
import sys
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from .diarization import DiarizationEngine, SpeakerTurn, apply_diarization, count_turn_speakers
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


@dataclass
class TranscriptionResult:
    text: str
    segments: list[TranscriptSegment]
    diarization_status: str = "disabled"
    speaker_count: int = 0
    raw_speaker_count: int = 0
    diarization_turns: list[SpeakerTurn] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)

    def __iter__(self):
        yield self.text
        yield self.segments


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

    def transcribe(
        self,
        audio_path: Path,
        language: str = "ru",
        expected_speakers: int | None = None,
    ) -> TranscriptionResult:
        started_at = time.perf_counter()
        timings: dict[str, float] = {}
        warnings: list[str] = []
        model = self._load_model()
        asr_started_at = time.perf_counter()
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
        timings["asr_seconds"] = round(time.perf_counter() - asr_started_at, 3)
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
            warnings.append("ASR returned no transcript segments.")
            timings["total_transcriber_seconds"] = round(time.perf_counter() - started_at, 3)
            return TranscriptionResult("", [], warnings=warnings, timings=timings)

        diarization_status = "disabled"
        turns: list[SpeakerTurn] = []
        if self.diarization_engine is not None:
            diarization_started_at = time.perf_counter()
            try:
                turns = self.diarization_engine.diarize(audio_path, expected_speakers=expected_speakers)
                timings["diarization_seconds"] = round(time.perf_counter() - diarization_started_at, 3)
                if turns:
                    segments = apply_diarization(segments, turns)
                    diarization_status = "succeeded"
                    raw_speaker_count = count_turn_speakers(turns)
                    if expected_speakers is not None and raw_speaker_count != expected_speakers:
                        warnings.append(
                            f"Diarization found {raw_speaker_count} raw speakers, expected {expected_speakers}."
                        )
                else:
                    diarization_status = "empty"
                    warnings.append("Diarization returned no speaker turns; text-only speaker assignment was used.")
            except Exception as exc:
                timings["diarization_seconds"] = round(time.perf_counter() - diarization_started_at, 3)
                diarization_status = "failed"
                warnings.append(f"Diarization failed; text-only speaker assignment was used: {exc}")
                LOGGER.exception("Diarization failed; falling back to text-only speaker assignment.")
        else:
            warnings.append("Diarization is disabled; speaker labels come from text-only heuristics.")

        text, processed_segments = postprocess_transcript(segments, language=language)
        speaker_count = len(
            {segment.get("speaker", "") for segment in processed_segments if segment.get("speaker")}
        )
        raw_speaker_count = count_turn_speakers(turns)
        if raw_speaker_count and speaker_count < raw_speaker_count:
            warnings.append(
                f"Post-processing collapsed speakers from {raw_speaker_count} raw clusters to {speaker_count} final labels."
            )
        if expected_speakers is not None and speaker_count != expected_speakers:
            warnings.append(f"Final transcript has {speaker_count} speakers, expected {expected_speakers}.")
        timings["total_transcriber_seconds"] = round(time.perf_counter() - started_at, 3)
        return TranscriptionResult(
            text=text,
            segments=processed_segments,
            diarization_status=diarization_status,
            speaker_count=speaker_count,
            raw_speaker_count=raw_speaker_count,
            diarization_turns=turns,
            warnings=warnings,
            timings=timings,
        )


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
