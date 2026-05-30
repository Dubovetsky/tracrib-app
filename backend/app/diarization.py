from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from .exports import TranscriptSegment, TranscriptWord


@dataclass(frozen=True)
class DiarizationConfig:
    enabled: bool = False
    model_name: str = "pyannote/speaker-diarization-3.1"
    device: str = "cuda"
    num_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None
    auth_token: str | None = None


@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    speaker: str


class DiarizationEngine(Protocol):
    def diarize(self, audio_path: Path, expected_speakers: int | None = None) -> list[SpeakerTurn]:
        ...


class PyannoteDiarizationEngine:
    def __init__(self, config: DiarizationConfig) -> None:
        self.config = config
        self._pipeline = None

    def _load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline

        from .transcriber import _add_windows_cuda_dll_dirs
        from .hf_env import remove_dead_local_proxy

        _add_windows_cuda_dll_dirs()
        remove_dead_local_proxy()
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

    def diarize(self, audio_path: Path, expected_speakers: int | None = None) -> list[SpeakerTurn]:
        pipeline = self._load_pipeline()
        kwargs: dict[str, int] = {}
        num_speakers = expected_speakers or self.config.num_speakers
        if num_speakers is not None:
            kwargs["num_speakers"] = num_speakers
        elif self.config.min_speakers is not None:
            kwargs["min_speakers"] = self.config.min_speakers
        if num_speakers is None and self.config.max_speakers is not None:
            kwargs["max_speakers"] = self.config.max_speakers

        diarization = annotation_from_pyannote_output(
            pipeline(load_audio_for_pyannote(audio_path), **kwargs)
        )
        turns: list[SpeakerTurn] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            turns.append(SpeakerTurn(float(turn.start), float(turn.end), str(speaker)))
        return turns


def annotation_from_pyannote_output(output: object) -> object:
    """Return the annotation object from pyannote's current or legacy pipeline output."""
    exclusive = getattr(output, "exclusive_speaker_diarization", None)
    if exclusive is not None:
        return exclusive
    speaker_diarization = getattr(output, "speaker_diarization", None)
    if speaker_diarization is not None:
        return speaker_diarization
    return output


def load_audio_for_pyannote(audio_path: Path) -> dict[str, object]:
    resolved_path = audio_path.resolve()
    try:
        import scipy.io.wavfile
        import torch

        sample_rate, samples = scipy.io.wavfile.read(str(resolved_path))
        tensor = torch.as_tensor(samples)
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        else:
            tensor = tensor.transpose(0, 1)
        if not tensor.is_floating_point():
            tensor = tensor.float()
            max_value = float(2 ** 15 if samples.dtype.itemsize <= 2 else 2 ** 31)
            tensor = tensor / max_value
        return {"waveform": tensor, "sample_rate": int(sample_rate)}
    except Exception:
        import torchaudio

        waveform, sample_rate = torchaudio.load(str(resolved_path))
    return {"waveform": waveform, "sample_rate": sample_rate}


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
        if segment.get("words"):
            processed.extend(split_segment_by_diarized_words(segment, turn_list, speaker_labels))
            continue

        raw_speaker = best_speaker_for_segment(segment, turn_list)
        if not raw_speaker:
            processed.append(segment)
            continue

        speaker = speaker_labels.setdefault(raw_speaker, f"Спикер {len(speaker_labels) + 1}")
        processed.append({**segment, "speaker": speaker, "raw_speaker": raw_speaker})

    return processed


def split_segment_by_diarized_words(
    segment: TranscriptSegment,
    turns: Iterable[SpeakerTurn],
    speaker_labels: dict[str, str],
) -> list[TranscriptSegment]:
    pieces: list[TranscriptSegment] = []
    current_speaker = ""
    current_raw_speaker = ""
    current_words: list[TranscriptWord] = []

    for word in segment.get("words", []):
        raw_speaker = best_speaker_for_word(word, turns) or best_speaker_for_segment(segment, turns)
        speaker = (
            speaker_labels.setdefault(raw_speaker, f"Спикер {len(speaker_labels) + 1}")
            if raw_speaker
            else ""
        )
        if current_words and speaker != current_speaker:
            pieces.append(build_segment_piece(current_words, current_speaker, current_raw_speaker))
            current_words = []
        current_speaker = speaker
        current_raw_speaker = raw_speaker or ""
        current_words.append(word)

    if current_words:
        pieces.append(build_segment_piece(current_words, current_speaker, current_raw_speaker))

    return pieces or [segment]


def build_segment_piece(
    words: list[TranscriptWord],
    speaker: str,
    raw_speaker: str = "",
) -> TranscriptSegment:
    text = " ".join(word["word"].strip() for word in words if word["word"].strip()).strip()
    piece: TranscriptSegment = {
        "start": words[0]["start"],
        "end": words[-1]["end"],
        "text": text,
    }
    if speaker:
        piece["speaker"] = speaker
    if raw_speaker:
        piece["raw_speaker"] = raw_speaker
    return piece


def count_turn_speakers(turns: Iterable[SpeakerTurn]) -> int:
    return len({turn.speaker for turn in turns})


def summarize_diarization(
    segments: Iterable[TranscriptSegment],
    turns: Iterable[SpeakerTurn],
) -> dict[str, int]:
    turn_list = list(turns)
    segments_with_switch = 0
    unassigned_words = 0
    assigned_words = 0
    for segment in segments:
        word_speakers = []
        for word in segment.get("words", []):
            speaker = best_speaker_for_word(word, turn_list)
            if speaker:
                assigned_words += 1
                word_speakers.append(speaker)
            else:
                unassigned_words += 1
        if len({speaker for speaker in word_speakers if speaker}) > 1:
            segments_with_switch += 1

    return {
        "speaker_clusters": count_turn_speakers(turn_list),
        "turns": len(turn_list),
        "segments_with_speaker_switch": segments_with_switch,
        "assigned_words": assigned_words,
        "unassigned_words": unassigned_words,
    }


def best_speaker_for_word(word: TranscriptWord, turns: Iterable[SpeakerTurn]) -> str | None:
    center = (word["start"] + word["end"]) / 2
    for turn in turns:
        if turn.start <= center <= turn.end:
            return turn.speaker
    return best_speaker_for_interval(word["start"], word["end"], turns)


def best_speaker_for_segment(segment: TranscriptSegment, turns: Iterable[SpeakerTurn]) -> str | None:
    return best_speaker_for_interval(segment["start"], segment["end"], turns)


def best_speaker_for_interval(start: float, end: float, turns: Iterable[SpeakerTurn]) -> str | None:
    scores: dict[str, float] = {}
    for turn in turns:
        overlap = overlap_seconds(start, end, turn.start, turn.end)
        if overlap > 0:
            scores[turn.speaker] = scores.get(turn.speaker, 0.0) + overlap

    if not scores:
        return None
    return max(scores.items(), key=lambda item: item[1])[0]


def overlap_seconds(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))
