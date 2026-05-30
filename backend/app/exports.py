from __future__ import annotations

from pathlib import Path
from typing import NotRequired, TypedDict


class TranscriptWord(TypedDict):
    start: float
    end: float
    word: str
    probability: NotRequired[float]


class TranscriptSegment(TypedDict):
    start: float
    end: float
    text: str
    speaker: NotRequired[str]
    raw_speaker: NotRequired[str]
    words: NotRequired[list[TranscriptWord]]
    no_speech_prob: NotRequired[float]
    avg_logprob: NotRequired[float]


def write_exports(text: str, segments: list[TranscriptSegment], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / "transcript.txt"
    txt_path.write_text(text.strip() + "\n", encoding="utf-8")
    return {"txt": txt_path}
