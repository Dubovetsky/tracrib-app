from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

from .exports import TranscriptSegment
from .postprocess import normalize_domain_terms, render_readable_text


_MAX_SEGMENTS_PER_REQUEST = 80
_MAX_CHARS_PER_REQUEST = 12_000
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(?P<json>.*?)\s*```", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class TextPolishConfig:
    provider: str = "auto"
    providers: tuple[str, ...] = ()
    model: str = "gpt-5-mini"
    timeout_seconds: float = 90.0
    openai_api_key: str | None = None


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    kind: str
    api_key: str | None
    model: str
    base_url: str
    extra: dict[str, str]


_DEFAULT_PROVIDER_PRIORITY = (
    "openai",
    "deepseek",
    "qwen",
    "grok",
    "gigachat",
    "yandexgpt",
    "mistral",
    "groq",
)


def polish_transcript(
    text: str,
    segments: list[TranscriptSegment],
    config: TextPolishConfig,
    language: str = "ru",
) -> tuple[str, list[TranscriptSegment]]:
    provider = config.provider.lower().strip()
    if provider in {"off", "none", "disabled"}:
        return text, segments

    locally_polished = polish_transcript_locally(segments, language=language)
    if provider == "local":
        return locally_polished

    for spec in build_provider_chain(config):
        try:
            return polish_transcript_with_provider(locally_polished[1], spec, config, language=language)
        except Exception:
            continue

    return locally_polished


def build_provider_chain(config: TextPolishConfig) -> list[ProviderSpec]:
    provider = config.provider.lower().strip()
    names = config.providers or parse_provider_list(os.getenv("TEXT_POLISH_PROVIDERS", ""))
    if not names:
        names = _DEFAULT_PROVIDER_PRIORITY if provider == "auto" else (provider,)

    chain: list[ProviderSpec] = []
    for name in names:
        spec = make_provider_spec(name, config)
        if spec and spec.api_key:
            chain.append(spec)
    return chain


def parse_provider_list(value: str) -> tuple[str, ...]:
    return tuple(part.strip().lower() for part in value.split(",") if part.strip())


def make_provider_spec(name: str, config: TextPolishConfig) -> ProviderSpec | None:
    normalized = name.lower().strip()
    aliases = {
        "xai": "grok",
        "giga": "gigachat",
        "gigachad": "gigachat",
        "giga_chat": "gigachat",
        "yandex": "yandexgpt",
        "dashscope": "qwen",
    }
    normalized = aliases.get(normalized, normalized)

    if normalized == "openai":
        return ProviderSpec(
            name="openai",
            kind="openai_compatible",
            api_key=config.openai_api_key or os.getenv("OPENAI_API_KEY"),
            model=os.getenv("OPENAI_TEXT_POLISH_MODEL", config.model),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            extra={},
        )
    if normalized == "deepseek":
        return ProviderSpec(
            name="deepseek",
            kind="openai_compatible",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            model=os.getenv("DEEPSEEK_TEXT_POLISH_MODEL", "deepseek-chat"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            extra={},
        )
    if normalized == "qwen":
        return ProviderSpec(
            name="qwen",
            kind="openai_compatible",
            api_key=os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY"),
            model=os.getenv("QWEN_TEXT_POLISH_MODEL", "qwen-plus"),
            base_url=os.getenv("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
            extra={},
        )
    if normalized == "grok":
        return ProviderSpec(
            name="grok",
            kind="openai_compatible",
            api_key=os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY"),
            model=os.getenv("GROK_TEXT_POLISH_MODEL", "grok-4"),
            base_url=os.getenv("GROK_BASE_URL", "https://api.x.ai/v1"),
            extra={},
        )
    if normalized == "mistral":
        return ProviderSpec(
            name="mistral",
            kind="openai_compatible",
            api_key=os.getenv("MISTRAL_API_KEY"),
            model=os.getenv("MISTRAL_TEXT_POLISH_MODEL", "mistral-large-latest"),
            base_url=os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1"),
            extra={},
        )
    if normalized == "groq":
        return ProviderSpec(
            name="groq",
            kind="openai_compatible",
            api_key=os.getenv("GROQ_API_KEY"),
            model=os.getenv("GROQ_TEXT_POLISH_MODEL", "llama-3.3-70b-versatile"),
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            extra={},
        )
    if normalized == "gigachat":
        return ProviderSpec(
            name="gigachat",
            kind="gigachat",
            api_key=os.getenv("GIGACHAT_ACCESS_TOKEN") or os.getenv("GIGACHAT_API_KEY"),
            model=os.getenv("GIGACHAT_TEXT_POLISH_MODEL", "GigaChat"),
            base_url=os.getenv("GIGACHAT_BASE_URL", "https://gigachat.devices.sberbank.ru/api/v1"),
            extra={},
        )
    if normalized == "yandexgpt":
        return ProviderSpec(
            name="yandexgpt",
            kind="yandexgpt",
            api_key=os.getenv("YANDEXGPT_API_KEY") or os.getenv("YANDEX_API_KEY"),
            model=os.getenv("YANDEXGPT_TEXT_POLISH_MODEL", "yandexgpt"),
            base_url=os.getenv("YANDEXGPT_BASE_URL", "https://llm.api.cloud.yandex.net/foundationModels/v1"),
            extra={"folder_id": os.getenv("YANDEXGPT_FOLDER_ID", "")},
        )
    return None


def polish_transcript_locally(
    segments: list[TranscriptSegment], language: str = "ru"
) -> tuple[str, list[TranscriptSegment]]:
    polished_segments: list[TranscriptSegment] = []
    for segment in segments:
        polished_segments.append({**segment, "text": normalize_domain_terms(segment["text"])})
    return render_readable_text(polished_segments, language=language), polished_segments


def polish_transcript_with_provider(
    segments: list[TranscriptSegment],
    spec: ProviderSpec,
    config: TextPolishConfig,
    language: str = "ru",
) -> tuple[str, list[TranscriptSegment]]:
    polished_segments: list[TranscriptSegment] = []
    with httpx.Client(timeout=config.timeout_seconds) as client:
        for chunk in chunk_segments(segments):
            replacements = request_segment_polish(client, chunk, spec, language=language)
            polished_segments.extend(apply_segment_replacements(chunk, replacements))

    return render_readable_text(polished_segments, language=language), polished_segments


def chunk_segments(segments: list[TranscriptSegment]) -> list[list[TranscriptSegment]]:
    chunks: list[list[TranscriptSegment]] = []
    current: list[TranscriptSegment] = []
    current_chars = 0

    for segment in segments:
        text_len = len(segment["text"])
        if current and (
            len(current) >= _MAX_SEGMENTS_PER_REQUEST
            or current_chars + text_len > _MAX_CHARS_PER_REQUEST
        ):
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(segment)
        current_chars += text_len

    if current:
        chunks.append(current)
    return chunks


def request_segment_polish(
    client: httpx.Client,
    segments: list[TranscriptSegment],
    spec: ProviderSpec,
    language: str = "ru",
) -> dict[int, str]:
    if spec.kind == "openai_compatible":
        return request_openai_compatible_segment_polish(client, segments, spec, language=language)
    if spec.kind == "gigachat":
        return request_gigachat_segment_polish(client, segments, spec, language=language)
    if spec.kind == "yandexgpt":
        return request_yandexgpt_segment_polish(client, segments, spec, language=language)
    raise RuntimeError(f"Unsupported text polish provider: {spec.name}")


def request_openai_compatible_segment_polish(
    client: httpx.Client,
    segments: list[TranscriptSegment],
    spec: ProviderSpec,
    language: str = "ru",
) -> dict[int, str]:
    response = client.post(
        f"{spec.base_url.rstrip('/')}/chat/completions",
        headers=build_bearer_headers(spec.api_key),
        json={
            "model": spec.model,
            "messages": build_chat_messages(segments, language=language),
            "temperature": 0,
        },
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return parse_polish_replacements(content)


def request_gigachat_segment_polish(
    client: httpx.Client,
    segments: list[TranscriptSegment],
    spec: ProviderSpec,
    language: str = "ru",
) -> dict[int, str]:
    response = client.post(
        f"{spec.base_url.rstrip('/')}/chat/completions",
        headers=build_bearer_headers(spec.api_key),
        json={
            "model": spec.model,
            "messages": build_chat_messages(segments, language=language),
            "temperature": 0,
        },
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return parse_polish_replacements(content)


def request_yandexgpt_segment_polish(
    client: httpx.Client,
    segments: list[TranscriptSegment],
    spec: ProviderSpec,
    language: str = "ru",
) -> dict[int, str]:
    folder_id = spec.extra.get("folder_id", "")
    if not folder_id:
        raise RuntimeError("YANDEXGPT_FOLDER_ID is not configured.")

    response = client.post(
        f"{spec.base_url.rstrip('/')}/completion",
        headers={
            "Authorization": f"Api-Key {spec.api_key}",
            "Content-Type": "application/json",
        },
        json={
            "modelUri": f"gpt://{folder_id}/{spec.model}/latest",
            "completionOptions": {"stream": False, "temperature": 0, "maxTokens": "8000"},
            "messages": build_yandex_messages(segments, language=language),
        },
    )
    response.raise_for_status()
    alternatives = response.json()["result"]["alternatives"]
    return parse_polish_replacements(alternatives[0]["message"]["text"])


def build_bearer_headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        raise RuntimeError("Cloud text polish API key is not configured.")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def build_chat_messages(segments: list[TranscriptSegment], language: str = "ru") -> list[dict[str, str]]:
    return [
        {"role": "system", "content": build_polish_instructions(language=language)},
        {"role": "user", "content": build_polish_payload(segments)},
    ]


def build_yandex_messages(segments: list[TranscriptSegment], language: str = "ru") -> list[dict[str, str]]:
    return [
        {"role": "system", "text": build_polish_instructions(language=language)},
        {"role": "user", "text": build_polish_payload(segments)},
    ]


def build_polish_payload(segments: list[TranscriptSegment]) -> str:
    payload_segments = [
        {
            "index": index,
            "speaker": segment.get("speaker", ""),
            "text": segment["text"],
        }
        for index, segment in enumerate(segments)
    ]
    return (
        "Верни строго JSON без markdown по схеме: "
        '{"segments":[{"index":0,"text":"исправленный текст"}]}. '
        "Количество и индексы сегментов должны совпадать с входом.\n"
        + json.dumps({"segments": payload_segments}, ensure_ascii=False)
    )


def build_polish_instructions(language: str = "ru") -> str:
    return (
        "Ты исправляешь текст русскоязычной транскрибации с вкраплениями английских IT и Agile терминов. "
        "Исправляй орфографию, пунктуацию, регистр, написание русских и английских слов, аббревиатуры и названия технологий. "
        "Правильно записывай IT/Agile сокращения: API, UI, UX, MVP, QA, CI/CD, PR, DoD, DoR, WIP, OKR, KPI, SLA, SLO, SLI, "
        "SQL, JSON, XML, YAML, HTTP, HTTPS, REST, SDK, CLI, IDE, DB, DNS, URL, URI, UUID, OAuth, SSO, JWT, RBAC, ACL, "
        "AI, ML, LLM, NLP, OCR, ASR, ETL, CRM, ERP, CDN, VPN, SSH, TLS, PDF, CSV, XLSX, DOCX. "
        "Не пересказывай, не сокращай, не добавляй новые факты и не меняй смысл. "
        "Сохраняй порядок сегментов и возвращай только исправленный текст каждого сегмента. "
        f"Основной язык: {language}."
    )


def parse_polish_replacements(content: str) -> dict[int, str]:
    parsed = json.loads(extract_json_text(content))
    return {
        int(item["index"]): normalize_domain_terms(str(item["text"]))
        for item in parsed.get("segments", [])
        if isinstance(item, dict) and "index" in item and "text" in item
    }


def extract_json_text(content: str) -> str:
    stripped = content.strip()
    match = _JSON_BLOCK_RE.fullmatch(stripped)
    if match:
        return match.group("json").strip()
    return stripped


def apply_segment_replacements(
    segments: list[TranscriptSegment], replacements: dict[int, str]
) -> list[TranscriptSegment]:
    polished: list[TranscriptSegment] = []
    for index, segment in enumerate(segments):
        replacement = replacements.get(index)
        if replacement:
            polished.append({**segment, "text": replacement})
        else:
            polished.append({**segment, "text": normalize_domain_terms(segment["text"])})
    return polished
