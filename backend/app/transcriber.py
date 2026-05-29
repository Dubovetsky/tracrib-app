from __future__ import annotations

import os
import site
import sys
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, NamedTuple

from .diarization import (
    DiarizationEngine,
    SpeakerTurn,
    apply_diarization,
    count_turn_speakers,
    summarize_diarization,
)
from .exports import TranscriptSegment, TranscriptWord
from .hf_env import remove_dead_local_proxy
from .postprocess import postprocess_transcript


LOGGER = logging.getLogger("transcrib_app.backend")
_CUDA_DLL_DIRS: list[object] = []
_CUDA_DLL_DIRS_ADDED = False
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")


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
    raw_text: str = ""
    raw_segments: list[TranscriptSegment] = field(default_factory=list)
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
        accurate_model_name: str | None = None,
        diarization_engine: DiarizationEngine | None = None,
        initial_prompt: str | None = None,
        hotwords: str | None = None,
        preserve_asr_words: bool = True,
    ) -> None:
        self.model_name = model_name
        self.accurate_model_name = accurate_model_name or model_name
        self.device = device
        self.compute_type = compute_type
        self.fallback_compute_type = fallback_compute_type
        self.diarization_engine = diarization_engine
        self.initial_prompt = initial_prompt
        self.hotwords = hotwords
        self.preserve_asr_words = preserve_asr_words
        self._models: dict[str, object] = {}

    def _load_model(self, model_name: str | None = None):
        selected_model = model_name or self.model_name
        if selected_model in self._models:
            return self._models[selected_model]

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
                model = WhisperModel(
                    selected_model,
                    device=device,
                    compute_type=compute_type,
                )
                self.device = device
                self.compute_type = compute_type
                self._models[selected_model] = model
                return model
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
        asr_quality: str = "balanced",
        participant_names: str = "",
        custom_vocabulary: str = "",
        source_duration_seconds: object = None,
        progress_callback: Callable[[str, float, str], None] | None = None,
        raw_asr_callback: Callable[[str, list[TranscriptSegment]], None] | None = None,
        run_diarization: bool = True,
    ) -> TranscriptionResult:
        started_at = time.perf_counter()
        timings: dict[str, float] = {}
        warnings: list[str] = []
        normalized_quality = normalize_asr_quality(asr_quality)
        selected_model = self.accurate_model_name if normalized_quality == "accurate" else self.model_name
        try:
            model = self._load_model(selected_model)
        except TranscriptionError as exc:
            if normalized_quality != "accurate":
                raise
            warnings.append(f"Accurate ASR model unavailable; falling back to {self.model_name}: {exc}")
            selected_model = self.model_name
            model = self._load_model(selected_model)
        if progress_callback:
            progress_callback(
                "asr",
                8.0,
                f"ASR model={selected_model}, device={self.device}, compute={self.compute_type}",
            )
        LOGGER.info(
            "ASR start: model=%s quality=%s device=%s compute=%s",
            selected_model,
            normalized_quality,
            self.device,
            self.compute_type,
        )
        asr_started_at = time.perf_counter()
        prompt = "" if normalized_quality == "fast" else build_quality_prompt(self.initial_prompt)
        hotwords = "" if normalized_quality == "fast" else build_quality_prompt(self.hotwords)
        prompt_echo_terms = extract_prompt_echo_terms(participant_names, custom_vocabulary)
        generated_segments, _ = model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
            word_timestamps=normalized_quality != "fast",
            condition_on_previous_text=False,
            initial_prompt=prompt or None,
            hotwords=hotwords or None,
            **decode_options(normalized_quality),
        )
        segments: list[TranscriptSegment] = []
        duration = source_duration_seconds if isinstance(source_duration_seconds, (float, int)) else None
        for segment in generated_segments:
            text = segment.text.strip()
            if not text:
                continue
            if is_prompt_echo_text(text, prompt_echo_terms):
                warnings.append(f"ASR prompt-echo segment removed: {text[:120]}")
                continue
            stripped_echo_text = strip_prompt_echo_prefix(text, prompt_echo_terms)
            if stripped_echo_text != text:
                warnings.append(f"ASR prompt-echo prefix removed: {text[:120]}")
                text = stripped_echo_text
                if not text:
                    continue
            transcript_segment: TranscriptSegment = {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": text,
            }
            no_speech_prob = getattr(segment, "no_speech_prob", None)
            avg_logprob = getattr(segment, "avg_logprob", None)
            if no_speech_prob is not None:
                transcript_segment["no_speech_prob"] = float(no_speech_prob)
            if avg_logprob is not None:
                transcript_segment["avg_logprob"] = float(avg_logprob)
            words = extract_segment_words(segment)
            if words:
                transcript_segment["words"] = words
            segments.append(transcript_segment)
            if progress_callback and duration and duration > 0:
                audio_progress = min(1.0, max(0.0, float(segment.end) / float(duration)))
                asr_progress_span = 75.0 if normalized_quality == "fast" else 22.0
                progress_callback(
                    "asr",
                    8.0 + (audio_progress * asr_progress_span),
                    "Распознаем речь",
                )
        timings["asr_seconds"] = round(time.perf_counter() - asr_started_at, 3)
        if not segments:
            warnings.append("ASR returned no transcript segments.")
            timings["total_transcriber_seconds"] = round(time.perf_counter() - started_at, 3)
            return TranscriptionResult("", [], warnings=warnings, timings=timings)

        raw_segments = [dict(segment) for segment in segments]
        raw_text = render_raw_asr_text(raw_segments)
        if raw_asr_callback:
            raw_asr_callback(raw_text, raw_segments)
        quality_warnings = build_asr_quality_warnings(
            raw_segments,
            normalized_quality,
            selected_model,
            self.device,
            self.compute_type,
        )
        warnings.extend(quality_warnings)

        diarization_status = "disabled"
        turns: list[SpeakerTurn] = []
        raw_speaker_count = 0
        effective_run_diarization = run_diarization and normalized_quality == "accurate"
        if self.diarization_engine is not None and effective_run_diarization:
            diarization_started_at = time.perf_counter()
            if progress_callback:
                progress_callback("diarization", 32.0, "Разделяем участников по голосам")
            try:
                turns = self.diarization_engine.diarize(audio_path, expected_speakers=expected_speakers)
                timings["diarization_seconds"] = round(time.perf_counter() - diarization_started_at, 3)
                if turns:
                    diarization_summary = summarize_diarization(segments, turns)
                    segments = apply_diarization(segments, turns)
                    diarization_status = "succeeded"
                    raw_speaker_count = count_turn_speakers(turns)
                    warnings.append(f"Diarization summary: {diarization_summary}.")
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
        elif normalized_quality == "balanced":
            lightweight_started_at = time.perf_counter()
            if progress_callback:
                progress_callback("diarization", 72.0, "Легко разделяем реплики")
            segments, raw_speaker_count = apply_lightweight_speaker_segmentation(
                segments,
                expected_speakers=expected_speakers,
            )
            timings["lightweight_diarization_seconds"] = round(time.perf_counter() - lightweight_started_at, 3)
            diarization_status = "lightweight"
            warnings.append(
                "Lightweight speaker separation used bounded text/timing heuristics; full acoustic diarization was not run."
            )
        else:
            if self.diarization_engine is not None and not effective_run_diarization:
                warnings.append(f"Diarization skipped by {normalized_quality} ASR mode; speaker labels come from text-only heuristics.")
            else:
                warnings.append("Diarization is disabled; speaker labels come from text-only heuristics.")

        if progress_callback:
            progress_callback("postprocess", 88.0, "Проверяем структуру текста")
        text, processed_segments = postprocess_transcript(
            segments,
            language=language,
            preserve_words=self.preserve_asr_words,
            allow_text_speaker_guess=normalized_quality == "balanced",
        )
        speaker_count = len(
            {segment.get("speaker", "") for segment in processed_segments if segment.get("speaker")}
        )
        if turns:
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
            raw_text=raw_text,
            raw_segments=raw_segments,
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
        extracted_word: TranscriptWord = {"start": float(start), "end": float(end), "word": text}
        probability = getattr(word, "probability", None)
        if probability is not None:
            extracted_word["probability"] = float(probability)
        extracted.append(extracted_word)
    return extracted


def apply_lightweight_speaker_segmentation(
    segments: list[TranscriptSegment],
    expected_speakers: int | None = None,
) -> tuple[list[TranscriptSegment], int]:
    if not segments:
        return segments, 0
    speaker_count = expected_speakers if expected_speakers and 1 < expected_speakers <= 6 else 2
    current_index = 0
    assigned: list[TranscriptSegment] = []
    previous: TranscriptSegment | None = None
    for segment in segments:
        if previous and should_switch_lightweight_speaker(previous, segment):
            current_index = (current_index + 1) % speaker_count
        speaker = f"Спикер {current_index + 1}"
        assigned_segment = {**segment, "speaker": speaker, "raw_speaker": f"lightweight_{current_index + 1}"}
        assigned.append(assigned_segment)
        previous = assigned_segment
    used = {segment.get("speaker", "") for segment in assigned if segment.get("speaker")}
    return assigned, len(used)


def should_switch_lightweight_speaker(previous: TranscriptSegment, current: TranscriptSegment) -> bool:
    previous_text = previous["text"].strip()
    current_text = current["text"].strip()
    gap = max(0.0, float(current["start"]) - float(previous["end"]))
    if previous_text.endswith("?") and gap <= 12.0:
        return True
    if 1.0 <= gap <= 8.0 and len(current_text) <= 260:
        return True
    if gap > 8.0 and len(previous_text) <= 320 and len(current_text) <= 320:
        return True
    return False


def render_raw_asr_text(segments: list[TranscriptSegment]) -> str:
    return "\n".join(segment["text"].strip() for segment in segments if segment["text"].strip()).strip()


def normalize_asr_quality(value: str | None) -> str:
    normalized = (value or "balanced").strip().lower()
    return normalized if normalized in {"fast", "balanced", "accurate"} else "balanced"


def decode_options(quality: str) -> dict[str, object]:
    if quality == "accurate":
        return {"beam_size": 8, "best_of": 5, "patience": 1.2, "temperature": [0.0, 0.2]}
    if quality == "fast":
        return {"beam_size": 1}
    return {"beam_size": 5, "best_of": 3}


def build_quality_prompt(*parts: str | None) -> str:
    clean_parts = [" ".join((part or "").strip().split()) for part in parts if (part or "").strip()]
    return ". ".join(clean_parts)


def extract_prompt_echo_terms(*parts: str | None) -> set[str]:
    terms: set[str] = set()
    for part in parts:
        for word in _WORD_RE.findall(part or ""):
            normalized = word.lower()
            if len(normalized) >= 2:
                terms.add(normalized)
    return terms


def is_prompt_echo_text(text: str, prompt_terms: set[str]) -> bool:
    normalized_text = " ".join(_WORD_RE.findall(text.lower()))
    if not normalized_text:
        return False
    if any(marker in normalized_text for marker in (
        "встреча на русском",
        "русская деловая встреча",
        "process terminology",
        "возможные термины",
        "термины и имена",
    )):
        return True
    if not prompt_terms:
        return False
    words = normalized_text.split()
    if len(words) < 3:
        return False
    prompt_word_count = sum(1 for word in words if word in prompt_terms)
    prompt_ratio = prompt_word_count / len(words)
    unique_words = set(words)
    non_prompt_words = unique_words - prompt_terms
    if prompt_ratio >= 0.72 and len(non_prompt_words) <= 2:
        return True
    if has_repeated_prompt_phrase(words, prompt_terms):
        return True
    return False


def strip_prompt_echo_prefix(text: str, prompt_terms: set[str]) -> str:
    if not prompt_terms:
        return text
    stripped = text.strip()
    parts = re.split(r"(?<=[.!?…])\s+", stripped, maxsplit=3)
    removed_any = False
    while parts and is_prompt_echo_text(parts[0], prompt_terms):
        parts.pop(0)
        removed_any = True
    return " ".join(parts).strip() if removed_any else text


def has_repeated_prompt_phrase(words: list[str], prompt_terms: set[str]) -> bool:
    if len(words) < 6:
        return False
    for size in range(2, min(6, len(words) // 2) + 1):
        chunks = [tuple(words[index:index + size]) for index in range(0, len(words) - size + 1, size)]
        repeated_prompt_chunks = 0
        previous: tuple[str, ...] | None = None
        for chunk in chunks:
            if previous == chunk and all(word in prompt_terms for word in chunk):
                repeated_prompt_chunks += 1
            previous = chunk
        if repeated_prompt_chunks >= 2:
            return True
    return False


def build_asr_quality_warnings(
    segments: list[TranscriptSegment],
    quality: str,
    model_name: str,
    device: str = "",
    compute_type: str = "",
) -> list[str]:
    device_part = f", device={device}, compute={compute_type}" if device or compute_type else ""
    warnings: list[str] = [f"ASR quality={quality}, model={model_name}{device_part}."]
    low_confidence_words = 0
    one_character_segments = 0
    for segment in segments:
        if len(segment.get("text", "").strip()) <= 1:
            one_character_segments += 1
        for word in segment.get("words", []):
            probability = word.get("probability")
            if isinstance(probability, (float, int)) and probability < 0.35:
                low_confidence_words += 1
    if low_confidence_words:
        warnings.append(f"ASR low-confidence words detected: {low_confidence_words}.")
    if one_character_segments:
        warnings.append(f"ASR suspicious one-character segments detected: {one_character_segments}.")
    return warnings
