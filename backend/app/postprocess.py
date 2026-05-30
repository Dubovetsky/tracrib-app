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
_INVALID_EXPLICIT_SPEAKER_NAMES = {
    "\u0430",
    "\u0431\u0435\u0437",
    "\u0432",
    "\u0432\u043e",
    "\u0434\u0430",
    "\u0434\u043b\u044f",
    "\u0434\u043e",
    "\u0435\u0441\u043b\u0438",
    "\u0438\u0437",
    "\u043a",
    "\u043a\u0430\u043a",
    "\u043a\u0430\u043a\u0430\u044f",
    "\u043a\u0430\u043a\u0438\u0435",
    "\u043a\u0430\u043a\u043e\u0439",
    "\u043a\u043e\u0433\u0434\u0430",
    "\u043a\u0442\u043e",
    "\u043d\u0430",
    "\u043d\u043e",
    "\u043e",
    "\u043e\u0442",
    "\u043f\u043e",
    "\u043f\u043e\u0434",
    "\u043f\u0440\u0438",
    "\u043f\u0440\u043e",
    "\u0441",
    "\u0441\u043e",
    "\u0442\u043e",
    "\u0447\u0442\u043e",
    "\u044d\u0442\u043e",
    "adr",
    "api",
    "edr",
    "idr",
    "it",
    "pmi",
    "\u0430\u0440\u0431\u0438\u0442\u0440",
    "\u0447\u0435\u043d\u044c",
    "\u0447\u0435\u043d\u044c-\u0447\u0435\u043d\u044c-\u0447\u0435\u043d\u044c",
}
_SPACE_RE = re.compile(r"\s+")
_DOTTED_EN_ABBREVIATION_RE = re.compile(r"\b(?:[A-Za-z]\.\s*){2,}")
_TRAILING_ARTIFACT_RE = re.compile(
    r"(?:^|\s+)"
    r"(?:"
    r"субтитры\s+(?:сделал[аи]?|подготовил[аи]?|создал[аи]?|перев[её]л[аи]?|добавил[аи]?)\s+[\w .@-]+|"
    r"редактор\s+субтитров\s*[:\-—]?\s*[\w .@-]*|"
    r"subtitles?\s+(?:by|created by|made by)\s+[\w .@-]+|"
    r"caption(?:ing|s)?\s+by\s+[\w .@-]+|"
    r"спасибо\s+за\s+просмотр|"
    r"продолжение\s+следует"
    r")"
    r"[.!?…]*\s*$",
    re.IGNORECASE,
)
_SPOKEN_SEPARATOR_RE = r"(?:\s+|[/\\+-]\s*)"
_SPOKEN_IT_AGILE_ABBREVIATIONS = {
    "Jira": (("джира",), ("джиру",), ("джире",), ("джиры",)),
    "API": (("эй", "пи", "ай"), ("а", "пи", "ай"), ("апи",)),
    "UI": (("ю", "ай"),),
    "UX": (("ю", "икс"),),
    "MVP": (("эм", "ви", "пи"),),
    "QA": (("кью", "эй"),),
    "CI/CD": (("си", "ай", "си", "ди"),),
    "CI": (("си", "ай"),),
    "CD": (("си", "ди"),),
    "PR": (("пи", "ар"),),
    "SQL": (("эс", "кью", "эл"), ("эс", "кью", "эль"), ("сиквел",)),
    "JSON": (("джей", "сон"), ("джейсон",)),
    "XML": (("икс", "эм", "эл"), ("икс", "эм", "эль")),
    "YAML": (("ямл",), ("ямал",), ("йамл",)),
    "HTTP": (("эйч", "ти", "ти", "пи"), ("аш", "ти", "ти", "пи")),
    "HTTPS": (("эйч", "ти", "ти", "пи", "эс"), ("аш", "ти", "ти", "пи", "эс")),
    "HTML": (("эйч", "ти", "эм", "эл"), ("эйч", "ти", "эм", "эль"), ("аш", "ти", "эм", "эл"), ("аш", "ти", "эм", "эль")),
    "CSS": (("си", "эс", "эс"),),
    "JS": (("джей", "эс"),),
    "TS": (("ти", "эс"),),
    "REST": (("рест",),),
    "CRUD": (("круд",),),
    "SDK": (("эс", "ди", "кей"),),
    "CLI": (("си", "эл", "ай"), ("си", "эль", "ай")),
    "IDE": (("ай", "ди", "и"), ("ай", "ди", "е")),
    "DB": (("ди", "би"),),
    "DNS": (("ди", "эн", "эс"),),
    "URL": (("ю", "ар", "эл"),),
    "URI": (("ю", "ар", "ай"),),
    "UUID": (("ю", "ю", "ай", "ди"),),
    "ID": (("ай", "ди"), ("айди",)),
    "IP": (("ай", "пи"), ("айпи",)),
    "OAuth": (("о", "аут"), ("оу", "аут")),
    "SSO": (("эс", "эс", "о"),),
    "JWT": (("джей", "дабл", "ю", "ти"), ("джей", "дабл", "ю", "т")),
    "RBAC": (("ар", "би", "эй", "си"),),
    "ACL": (("эй", "си", "эл"), ("эй", "си", "эль")),
    "OKR": (("о", "кей", "ар"),),
    "KPI": (("кей", "пи", "ай"),),
    "SLA": (("эс", "эл", "эй"), ("эс", "эль", "эй")),
    "SLO": (("эс", "эл", "о"), ("эс", "эль", "о")),
    "SLI": (("эс", "эл", "ай"), ("эс", "эль", "ай")),
    "WIP": (("дабл", "ю", "ай", "пи"),),
    "DoD": (("ди", "о", "ди"),),
    "DoR": (("ди", "о", "ар"),),
    "RACI": (("рейси",), ("раси",)),
    "SMART": (("смарт",),),
    "CPU": (("си", "пи", "ю"),),
    "GPU": (("джи", "пи", "ю"),),
    "RAM": (("рэм",),),
    "AI": (("эй", "ай"),),
    "ML": (("эм", "эл"), ("эм", "эль")),
    "LLM": (("эл", "эл", "эм"), ("эль", "эль", "эм")),
    "NLP": (("эн", "эл", "пи"), ("эн", "эль", "пи")),
    "OCR": (("о", "си", "ар"),),
    "ASR": (("эй", "эс", "ар"),),
    "STT": (("эс", "ти", "ти"),),
    "TTS": (("ти", "ти", "эс"),),
    "ETL": (("и", "ти", "эл"), ("и", "ти", "эль")),
    "BI": (("би", "ай"),),
    "CRM": (("си", "ар", "эм"),),
    "ERP": (("и", "ар", "пи"),),
    "CMS": (("си", "эм", "эс"),),
    "CDN": (("си", "ди", "эн"),),
    "VPN": (("ви", "пи", "эн"),),
    "SSH": (("эс", "эс", "эйч"), ("эс", "эс", "аш")),
    "FTP": (("эф", "ти", "пи"),),
    "SFTP": (("эс", "эф", "ти", "пи"),),
    "SSL": (("эс", "эс", "эл"), ("эс", "эс", "эль")),
    "TLS": (("ти", "эл", "эс"), ("ти", "эль", "эс")),
    "TCP": (("ти", "си", "пи"),),
    "UDP": (("ю", "ди", "пи"),),
    "PDF": (("пи", "ди", "эф"),),
    "CSV": (("си", "эс", "ви"),),
    "XLSX": (("икс", "эл", "эс", "икс"), ("икс", "эль", "эс", "икс")),
    "DOCX": (("док", "икс"), ("ди", "о", "си", "икс")),
}
_WRITTEN_IT_AGILE_REPLACEMENTS = {
    "jira": "Jira",
    "ci/cd": "CI/CD",
    "okrs": "OKR",
    "kpis": "KPI",
    "api": "API",
    "ui": "UI",
    "ux": "UX",
    "mvp": "MVP",
    "qa": "QA",
    "ci": "CI",
    "cd": "CD",
    "pr": "PR",
    "sql": "SQL",
    "json": "JSON",
    "xml": "XML",
    "yaml": "YAML",
    "http": "HTTP",
    "https": "HTTPS",
    "html": "HTML",
    "css": "CSS",
    "js": "JS",
    "ts": "TS",
    "rest": "REST",
    "crud": "CRUD",
    "sdk": "SDK",
    "cli": "CLI",
    "ide": "IDE",
    "db": "DB",
    "dns": "DNS",
    "url": "URL",
    "uri": "URI",
    "uuid": "UUID",
    "id": "ID",
    "ip": "IP",
    "oauth": "OAuth",
    "sso": "SSO",
    "jwt": "JWT",
    "rbac": "RBAC",
    "acl": "ACL",
    "okr": "OKR",
    "kpi": "KPI",
    "sla": "SLA",
    "slo": "SLO",
    "sli": "SLI",
    "wip": "WIP",
    "dod": "DoD",
    "dor": "DoR",
    "raci": "RACI",
    "smart": "SMART",
    "cpu": "CPU",
    "gpu": "GPU",
    "ram": "RAM",
    "ai": "AI",
    "ml": "ML",
    "llm": "LLM",
    "nlp": "NLP",
    "ocr": "OCR",
    "asr": "ASR",
    "stt": "STT",
    "tts": "TTS",
    "etl": "ETL",
    "bi": "BI",
    "crm": "CRM",
    "erp": "ERP",
    "cms": "CMS",
    "cdn": "CDN",
    "vpn": "VPN",
    "ssh": "SSH",
    "ftp": "FTP",
    "sftp": "SFTP",
    "ssl": "SSL",
    "tls": "TLS",
    "tcp": "TCP",
    "udp": "UDP",
    "pdf": "PDF",
    "csv": "CSV",
    "xlsx": "XLSX",
    "docx": "DOCX",
}


def _spoken_abbreviation_pattern(words: tuple[str, ...]) -> str:
    escaped_words = [re.escape(word) for word in words]
    return r"\b" + _SPOKEN_SEPARATOR_RE.join(escaped_words) + r"\b"


def _written_abbreviation_pattern(source: str) -> str:
    escaped = re.escape(source).replace(r"\/", r"\s*/\s*")
    return r"\b" + escaped + r"\b"


_SPOKEN_IT_AGILE_REPLACEMENT_RES = [
    (re.compile(_spoken_abbreviation_pattern(words), re.IGNORECASE), replacement)
    for replacement, variants in sorted(
        _SPOKEN_IT_AGILE_ABBREVIATIONS.items(),
        key=lambda item: max(len(words) for words in item[1]),
        reverse=True,
    )
    for words in sorted(variants, key=len, reverse=True)
]
_WRITTEN_IT_AGILE_REPLACEMENT_RES = [
    (re.compile(_written_abbreviation_pattern(source), re.IGNORECASE), replacement)
    for source, replacement in _WRITTEN_IT_AGILE_REPLACEMENTS.items()
]

_MAX_PARAGRAPH_SENTENCES = 3
_MAX_PARAGRAPH_CHARS = 520
_ANSWER_GAP_SECONDS = 12.0


def postprocess_transcript(
    segments: list[TranscriptSegment],
    language: str = "ru",
    preserve_words: bool = False,
    allow_text_speaker_guess: bool = False,
) -> tuple[str, list[TranscriptSegment]]:
    cleaned_segments = list(segments) if preserve_words else strip_trailing_artifacts(segments)
    processed_segments = assign_speakers(
        cleaned_segments,
        preserve_words=preserve_words,
        allow_text_speaker_guess=allow_text_speaker_guess,
    )
    return render_readable_text(processed_segments, language=language), processed_segments


def strip_trailing_artifacts(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    processed = list(segments)

    for index in range(len(processed) - 1, -1, -1):
        original_text = normalize_spaces(processed[index]["text"])
        cleaned_text = strip_trailing_artifact_text(original_text)
        if not cleaned_text:
            processed.pop(index)
            continue

        if cleaned_text != original_text:
            processed[index] = {**processed[index], "text": cleaned_text}
        break

    return processed


def strip_trailing_artifact_text(text: str) -> str:
    cleaned = normalize_spaces(text)
    while cleaned:
        next_cleaned = normalize_spaces(_TRAILING_ARTIFACT_RE.sub("", cleaned))
        if next_cleaned == cleaned:
            break
        cleaned = next_cleaned
    return cleaned


def assign_speakers(
    segments: list[TranscriptSegment],
    preserve_words: bool = False,
    allow_text_speaker_guess: bool = False,
) -> list[TranscriptSegment]:
    speaker_by_name: dict[str, str] = {}
    name_by_diarized_speaker: dict[str, str] = {}
    unknown_speakers = ["Спикер 1", "Спикер 2"]
    current_speaker = unknown_speakers[0]
    previous: TranscriptSegment | None = None
    processed: list[TranscriptSegment] = []

    for segment in segments:
        text = normalize_spaces(segment["text"])
        normalized_for_speaker_detection = normalize_domain_terms(text)
        explicit_name, explicit_text = extract_explicit_speaker(normalized_for_speaker_detection)
        intro_name = extract_self_intro_name(text)
        diarized_speaker = normalize_spaces(segment.get("speaker", ""))
        if explicit_name and not preserve_words:
            text = explicit_text
        elif not preserve_words:
            text = normalized_for_speaker_detection

        if explicit_name:
            current_speaker = speaker_by_name.setdefault(explicit_name, explicit_name)
            if diarized_speaker:
                name_by_diarized_speaker[diarized_speaker] = current_speaker
        elif intro_name and current_speaker.startswith("Спикер "):
            current_speaker = speaker_by_name.setdefault(intro_name, intro_name)
            if diarized_speaker:
                name_by_diarized_speaker[diarized_speaker] = current_speaker
        elif diarized_speaker:
            current_speaker = name_by_diarized_speaker.get(diarized_speaker, diarized_speaker)
        elif allow_text_speaker_guess and previous and is_likely_answer_turn(previous, segment):
            current_speaker = other_unknown_speaker(previous.get("speaker", current_speaker), unknown_speakers)

        processed_segment: TranscriptSegment = {
            "start": segment["start"],
            "end": segment["end"],
            "text": text,
            "speaker": current_speaker,
        }
        if segment.get("raw_speaker"):
            processed_segment["raw_speaker"] = segment["raw_speaker"]
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
    return _DOTTED_EN_ABBREVIATION_RE.sub(_protect_dotted_abbreviation_match, text)


def _protect_dotted_abbreviation_match(match: re.Match[str]) -> str:
    return match.group(0).replace(".", "<dot>")


def _restore_abbreviation_marks(text: str) -> str:
    return text.replace("<dot>", ".")


def extract_explicit_speaker(text: str) -> tuple[str | None, str]:
    match = _LABEL_RE.match(text)
    if not match:
        return None, text
    name = normalize_name(match.group("name"))
    if not is_plausible_explicit_speaker_name(name):
        return None, text
    return name, normalize_spaces(match.group("text"))


def is_plausible_explicit_speaker_name(name: str) -> bool:
    normalized = normalize_spaces(name).lower()
    if normalized in _INVALID_EXPLICIT_SPEAKER_NAMES:
        return False
    if normalized.upper() in _SPOKEN_IT_AGILE_ABBREVIATIONS:
        return False
    parts = normalized.split()
    return not any(part in _INVALID_EXPLICIT_SPEAKER_NAMES for part in parts)


def extract_self_intro_name(text: str) -> str | None:
    match = _SELF_INTRO_RE.search(text)
    if not match:
        return None
    return normalize_name(match.group("name"))


def normalize_name(name: str) -> str:
    return " ".join(part.capitalize() for part in normalize_spaces(name).split())


def normalize_spaces(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def normalize_domain_terms(text: str) -> str:
    normalized = text
    for pattern, replacement in _SPOKEN_IT_AGILE_REPLACEMENT_RES:
        normalized = pattern.sub(replacement, normalized)
    for pattern, replacement in _WRITTEN_IT_AGILE_REPLACEMENT_RES:
        normalized = pattern.sub(replacement, normalized)
    return normalize_spaces(normalized)


def is_likely_answer_turn(previous: TranscriptSegment, segment: TranscriptSegment) -> bool:
    gap = max(0.0, segment["start"] - previous["end"])
    return gap <= _ANSWER_GAP_SECONDS and previous["text"].rstrip().endswith("?")


def other_unknown_speaker(current: str, unknown_speakers: list[str]) -> str:
    if current == unknown_speakers[0]:
        return unknown_speakers[1]
    return unknown_speakers[0]
