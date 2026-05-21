from __future__ import annotations

from pathlib import Path
from typing import Iterable, NotRequired, TypedDict


class TranscriptWord(TypedDict):
    start: float
    end: float
    word: str


class TranscriptSegment(TypedDict):
    start: float
    end: float
    text: str
    speaker: NotRequired[str]
    words: NotRequired[list[TranscriptWord]]


def format_srt_timestamp(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def format_vtt_timestamp(seconds: float) -> str:
    return format_srt_timestamp(seconds).replace(",", ".")


def render_srt(segments: Iterable[TranscriptSegment]) -> str:
    blocks = []
    for index, segment in enumerate(segments, start=1):
        text = render_subtitle_text(segment)
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_timestamp(segment['start'])} --> {format_srt_timestamp(segment['end'])}",
                    text,
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def render_vtt(segments: Iterable[TranscriptSegment]) -> str:
    blocks = ["WEBVTT", ""]
    for segment in segments:
        blocks.extend(
            [
                f"{format_vtt_timestamp(segment['start'])} --> {format_vtt_timestamp(segment['end'])}",
                render_subtitle_text(segment),
                "",
            ]
        )
    return "\n".join(blocks)


def render_subtitle_text(segment: TranscriptSegment) -> str:
    text = segment["text"].strip()
    speaker = segment.get("speaker", "").strip()
    if speaker:
        return f"{speaker}: {text}"
    return text


def write_exports(text: str, segments: list[TranscriptSegment], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / "transcript.txt"
    srt_path = output_dir / "transcript.srt"
    vtt_path = output_dir / "transcript.vtt"
    txt_path.write_text(text.strip() + "\n", encoding="utf-8")
    srt_path.write_text(render_srt(segments), encoding="utf-8")
    vtt_path.write_text(render_vtt(segments), encoding="utf-8")
    return {"txt": txt_path, "srt": srt_path, "vtt": vtt_path}
