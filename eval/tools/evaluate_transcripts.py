from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


TERMS = [
    "EADR",
    "ADR",
    "IDR",
    "DR",
    "RFC",
    "Jira",
    "AirPoint",
    "GSM",
    "CM",
    "TMH",
    "QA",
    "API",
    "UI",
    "UX",
    "MVP",
    "CI/CD",
]

SUSPECT_TERMS = [
    "АДР",
    "ЭАДР",
    "ЕАДР",
    "Эйдр",
    "Аирпоинт",
    "Эрпоинт",
    "Жира",
]

PLACEHOLDER_MARKERS = {"REFERENCE_STATUS: TODO_HUMAN", "TODO_HUMAN"}

SPEAKER_LINE_RE = re.compile(r"^\s*([^:\n]{1,40}):\s*$")
SPEAKER_INLINE_RE = re.compile(r"^\s*([^:\n]{1,40}):\s+(.+)$")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9/]+", re.UNICODE)


@dataclass(frozen=True)
class TextMetrics:
    chars: int
    words: int
    speaker_labels: dict[str, int]
    speaker_turns: int
    suspicious_labels: list[str]
    term_hits: dict[str, int]
    suspect_term_hits: dict[str, int]
    repeated_lines: list[str]


def normalize_words(text: str) -> list[str]:
    return [token.lower() for token in WORD_RE.findall(text)]


def normalize_chars(text: str) -> str:
    return "".join(normalize_words(text))


def edit_distance(left: list[str] | str, right: list[str] | str) -> int:
    previous = list(range(len(right) + 1))
    for i, left_item in enumerate(left, start=1):
        current = [i]
        for j, right_item in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left_item != right_item),
                )
            )
        previous = current
    return previous[-1]


def error_rate(reference: list[str] | str, hypothesis: list[str] | str) -> float | None:
    if not reference:
        return None
    return edit_distance(reference, hypothesis) / len(reference)


def is_placeholder(path: Path) -> bool:
    if not path.exists():
        return True
    text = path.read_text(encoding="utf-8")
    return any(marker in text for marker in PLACEHOLDER_MARKERS)


def strip_speaker_labels(text: str) -> str:
    cleaned: list[str] = []
    for line in text.splitlines():
        if SPEAKER_LINE_RE.match(line):
            continue
        inline = SPEAKER_INLINE_RE.match(line)
        cleaned.append(inline.group(2) if inline else line)
    return "\n".join(cleaned)


def analyze_text(text: str) -> TextMetrics:
    labels: Counter[str] = Counter()
    body_lines: list[str] = []
    suspicious: list[str] = []
    previous_label: str | None = None
    turns = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        label = None
        speaker_line = SPEAKER_LINE_RE.match(line)
        inline_line = SPEAKER_INLINE_RE.match(line)
        if speaker_line:
            label = speaker_line.group(1).strip()
        elif inline_line:
            label = inline_line.group(1).strip()
            body_lines.append(inline_line.group(2).strip())
        else:
            body_lines.append(line)

        if label:
            labels[label] += 1
            if label != previous_label:
                turns += 1
                previous_label = label
            if not re.search(r"(speaker|спикер|SPEAKER|\d)", label, re.IGNORECASE):
                suspicious.append(label)

    body = "\n".join(body_lines)
    line_counts = Counter(line for line in body_lines if len(line) >= 30)
    repeated = [line for line, count in line_counts.most_common(10) if count > 1]

    return TextMetrics(
        chars=len(body),
        words=len(normalize_words(body)),
        speaker_labels=dict(labels),
        speaker_turns=turns,
        suspicious_labels=sorted(set(suspicious)),
        term_hits={term: len(re.findall(rf"(?<!\w){re.escape(term)}(?!\w)", body, re.IGNORECASE)) for term in TERMS},
        suspect_term_hits={term: body.lower().count(term.lower()) for term in SUSPECT_TERMS},
        repeated_lines=repeated,
    )


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(sample: str, hypothesis_path: Path, reference_path: Path, speaker_reference_path: Path) -> dict:
    hypothesis = hypothesis_path.read_text(encoding="utf-8")
    hypothesis_body = strip_speaker_labels(hypothesis)
    reference_ready = not is_placeholder(reference_path)

    metrics = analyze_text(hypothesis)
    wer = None
    cer = None
    if reference_ready:
        reference = strip_speaker_labels(reference_path.read_text(encoding="utf-8"))
        wer = error_rate(normalize_words(reference), normalize_words(hypothesis_body))
        cer = error_rate(normalize_chars(reference), normalize_chars(hypothesis_body))

    speaker_ref = load_json(speaker_reference_path)
    speaker_ref_ready = speaker_ref.get("reference_status") != "TODO_HUMAN" and bool(speaker_ref.get("turns"))
    expected_speakers = len(speaker_ref.get("speakers", [])) if speaker_ref_ready else None

    return {
        "sample": sample,
        "hypothesis": str(hypothesis_path),
        "reference_ready": reference_ready,
        "speaker_reference_ready": speaker_ref_ready,
        "wer": wer,
        "cer": cer,
        "chars": metrics.chars,
        "words": metrics.words,
        "speaker_labels": metrics.speaker_labels,
        "speaker_label_count": len(metrics.speaker_labels),
        "speaker_turns": metrics.speaker_turns,
        "expected_speakers": expected_speakers,
        "suspicious_labels": metrics.suspicious_labels,
        "term_hits": metrics.term_hits,
        "suspect_term_hits": {key: value for key, value in metrics.suspect_term_hits.items() if value},
        "repeated_lines": metrics.repeated_lines,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("eval/reports/metrics.json"))
    parser.add_argument(
        "--sample",
        action="append",
        nargs=4,
        metavar=("NAME", "HYPOTHESIS", "REFERENCE", "SPEAKERS"),
        required=True,
    )
    args = parser.parse_args()

    reports = []
    for name, hypothesis, reference, speakers in args.sample:
        reports.append(
            build_report(
                name,
                args.repo / hypothesis,
                args.repo / reference,
                args.repo / speakers,
            )
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
