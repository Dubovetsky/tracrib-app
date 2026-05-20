from __future__ import annotations

import re

from .exports import TranscriptSegment


_LABEL_RE = re.compile(
    r"^\s*(?P<name>[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё-]{1,}(?:\s+[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё-]{1,}){0,2})\s*[:\-—]\s*(?P<text>.+)$"
)
_SELF_INTRO_RE = re.compile(
    r"\b(?:меня зовут|мое имя|моё имя)\s+(?P<name>[А-ЯЁ][а-яё-]{1,}(?:\s+[А-ЯЁ][а-яё-]{1,})?)\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZА-ЯЁ0-9\"«])")
_SPACE_RE = re.compile(r"\s+")

_MAX_PARAGRAPH_SENTENCES = 3
_MAX_PARAGRAPH_CHARS = 520
_ANSWER_GAP_SECONDS = 12.0


def postprocess_transcript(
    segments: list[TranscriptSegment], language: str = "ru"
) -> tuple[str, list[TranscriptSegment]]:
    processed_segments = assign_speakers(segments)
    return render_readable_text(processed_segments, language=language), processed_segments


def assign_speakers(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    speaker_by_name: dict[str, str] = {}
    unknown_speakers = ["Спикер 1", "Спикер 2"]
    current_speaker = unknown_speakers[0]
    previous: TranscriptSegment | None = None
    processed: list[TranscriptSegment] = []

    for segment in segments:
        text = normalize_spaces(segment["text"])
        explicit_name, text = extract_explicit_speaker(text)
        intro_name = extract_self_intro_name(text)

        if explicit_name:
            current_speaker = speaker_by_name.setdefault(explicit_name, explicit_name)
        elif intro_name and current_speaker.startswith("Спикер "):
            current_speaker = speaker_by_name.setdefault(intro_name, intro_name)
        elif previous and is_likely_answer_turn(previous, segment):
            current_speaker = other_unknown_speaker(previous.get("speaker", current_speaker), unknown_speakers)

        processed_segment: TranscriptSegment = {
            "start": segment["start"],
            "end": segment["end"],
            "text": text,
            "speaker": current_speaker,
        }
        processed.append(processed_segment)
        previous = processed_segment

    return processed


def render_readable_text(segments: list[TranscriptSegment], language: str = "ru") -> str:
    blocks: list[str] = []
    current_speaker = ""
    current_text_parts: list[str] = []

    for segment in segments:
        speaker = segment.get("speaker", "Спикер 1")
        text = normalize_spaces(segment["text"])
        if current_speaker and speaker != current_speaker:
            blocks.append(render_speaker_block(current_speaker, current_text_parts, language))
            current_text_parts = []
        current_speaker = speaker
        current_text_parts.append(text)

    if current_text_parts:
        blocks.append(render_speaker_block(current_speaker or "Спикер 1", current_text_parts, language))

    return "\n\n".join(block for block in blocks if block).strip()


def render_speaker_block(speaker: str, text_parts: list[str], language: str) -> str:
    text = normalize_spaces(" ".join(text_parts))
    paragraphs = split_paragraphs(text, language=language)
    if not paragraphs:
        return ""
    return f"{speaker}:\n" + "\n\n".join(paragraphs)


def split_paragraphs(text: str, language: str = "ru") -> list[str]:
    sentences = split_sentences(text, language=language)
    paragraphs: list[str] = []
    current: list[str] = []
    current_chars = 0

    for sentence in sentences:
        sentence_len = len(sentence)
        if current and (
            len(current) >= _MAX_PARAGRAPH_SENTENCES
            or current_chars + sentence_len > _MAX_PARAGRAPH_CHARS
        ):
            paragraphs.append(" ".join(current))
            current = []
            current_chars = 0
        current.append(sentence)
        current_chars += sentence_len

    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


def split_sentences(text: str, language: str = "ru") -> list[str]:
    text = normalize_spaces(text)
    if not text:
        return []

    protected = protect_common_abbreviations(text, language=language)
    sentences = [_restore_abbreviation_marks(part.strip()) for part in _SENTENCE_SPLIT_RE.split(protected)]
    return [sentence for sentence in sentences if sentence]


def protect_common_abbreviations(text: str, language: str) -> str:
    replacements = {
        "т. е.": "т<dot> е<dot>",
        "т.е.": "т<dot>е<dot>",
        "т. к.": "т<dot> к<dot>",
        "т.к.": "т<dot>к<dot>",
        "т. д.": "т<dot> д<dot>",
        "т.д.": "т<dot>д<dot>",
        "т. п.": "т<dot> п<dot>",
        "т.п.": "т<dot>п<dot>",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _restore_abbreviation_marks(text: str) -> str:
    return text.replace("<dot>", ".")


def extract_explicit_speaker(text: str) -> tuple[str | None, str]:
    match = _LABEL_RE.match(text)
    if not match:
        return None, text
    name = normalize_name(match.group("name"))
    return name, normalize_spaces(match.group("text"))


def extract_self_intro_name(text: str) -> str | None:
    match = _SELF_INTRO_RE.search(text)
    if not match:
        return None
    return normalize_name(match.group("name"))


def normalize_name(name: str) -> str:
    return " ".join(part.capitalize() for part in normalize_spaces(name).split())


def normalize_spaces(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def is_likely_answer_turn(previous: TranscriptSegment, segment: TranscriptSegment) -> bool:
    gap = max(0.0, segment["start"] - previous["end"])
    return gap <= _ANSWER_GAP_SECONDS and previous["text"].rstrip().endswith("?")


def other_unknown_speaker(current: str, unknown_speakers: list[str]) -> str:
    if current == unknown_speakers[0]:
        return unknown_speakers[1]
    return unknown_speakers[0]
