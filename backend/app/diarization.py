from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from .exports import TranscriptSegment


@dataclass(frozen=True)
class DiarizationConfig:
    enabled: bool = False
    model_name: str = "pyannote/speaker-diarization-3.1"
    device: str = "cuda"
    min_speakers: int | None = None
    max_speakers: int | None = None
    auth_token: str | None = None


@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    speaker: str


class DiarizationEngine(Protocol):
    def diarize(self, audio_path: Path) -> list[SpeakerTurn]:
        ...


class PyannoteDiarizationEngine:
    def __init__(self, config: DiarizationConfig) -> None:
        self.config = config
        self._pipeline = None

    def _load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline

        from .transcriber import _add_windows_cuda_dll_dirs

        _add_windows_cuda_dll_dirs()
        from pyannote.audio import Pipeline

        token = self.config.auth_token or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
        try:
            pipeline = Pipeline.from_pretrained(self.config.model_name, use_auth_token=token)
        except TypeError:
            pipeline = Pipeline.from_pretrained(self.config.model_name, token=token)

        if self.config.device:
            try:
                import torch

                pipeline.to(torch.device(self.config.device))
            except Exception:
                # Pyannote can still run on its default device; keep the job alive.
                pass

        self._pipeline = pipeline
        return pipeline

    def diarize(self, audio_path: Path) -> list[SpeakerTurn]:
        pipeline = self._load_pipeline()
        kwargs: dict[str, int] = {}
        if self.config.min_speakers is not None:
            kwargs["min_speakers"] = self.config.min_speakers
        if self.config.max_speakers is not None:
            kwargs["max_speakers"] = self.config.max_speakers

        diarization = pipeline(str(audio_path), **kwargs)
        turns: list[SpeakerTurn] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            turns.append(SpeakerTurn(float(turn.start), float(turn.end), str(speaker)))
        return turns


def build_diarization_engine(config: DiarizationConfig) -> DiarizationEngine | None:
    if not config.enabled:
        return None
    return PyannoteDiarizationEngine(config)


def apply_diarization(
    segments: list[TranscriptSegment],
    turns: Iterable[SpeakerTurn],
) -> list[TranscriptSegment]:
    turn_list = list(turns)
    speaker_labels: dict[str, str] = {}
    processed: list[TranscriptSegment] = []

    for segment in segments:
        raw_speaker = best_speaker_for_segment(segment, turn_list)
        if not raw_speaker:
            processed.append(segment)
            continue

        speaker = speaker_labels.setdefault(raw_speaker, f"Спикер {len(speaker_labels) + 1}")
        processed.append({**segment, "speaker": speaker})

    return processed


def best_speaker_for_segment(segment: TranscriptSegment, turns: Iterable[SpeakerTurn]) -> str | None:
    scores: dict[str, float] = {}
    for turn in turns:
        overlap = overlap_seconds(segment["start"], segment["end"], turn.start, turn.end)
        if overlap > 0:
            scores[turn.speaker] = scores.get(turn.speaker, 0.0) + overlap

    if not scores:
        return None
    return max(scores.items(), key=lambda item: item[1])[0]


def overlap_seconds(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))
