from backend.app.text_polish import (
    TextPolishConfig,
    build_provider_chain,
    parse_polish_replacements,
    polish_transcript,
)


def test_text_polish_auto_without_key_uses_local_rules():
    text, segments = polish_transcript(
        "Спикер 1:\nПроверим эй пи ай и си ай си ди.",
        [{"start": 0.0, "end": 2.0, "text": "Проверим эй пи ай и си ай си ди.", "speaker": "Спикер 1"}],
        TextPolishConfig(provider="auto", openai_api_key=None),
    )

    assert segments[0]["text"] == "Проверим API и CI/CD."
    assert "API и CI/CD" in text


def test_text_polish_off_keeps_original_text_and_segments():
    original_segments = [
        {"start": 0.0, "end": 2.0, "text": "Проверим эй пи ай.", "speaker": "Спикер 1"}
    ]

    text, segments = polish_transcript(
        "Спикер 1:\nПроверим эй пи ай.",
        original_segments,
        TextPolishConfig(provider="off", openai_api_key="test-key"),
    )

    assert text == "Спикер 1:\nПроверим эй пи ай."
    assert segments == original_segments


def test_text_polish_auto_falls_back_to_local_when_cloud_fails(monkeypatch):
    def fail_cloud(*args, **kwargs):
        raise RuntimeError("cloud unavailable")

    monkeypatch.setattr("backend.app.text_polish.polish_transcript_with_provider", fail_cloud)

    text, segments = polish_transcript(
        "Спикер 1:\nНужен джей сон и эс кью эл.",
        [{"start": 0.0, "end": 2.0, "text": "Нужен джей сон и эс кью эл.", "speaker": "Спикер 1"}],
        TextPolishConfig(provider="auto", openai_api_key="test-key"),
    )

    assert segments[0]["text"] == "Нужен JSON и SQL."
    assert "JSON и SQL" in text


def test_text_polish_specific_cloud_provider_still_falls_back_to_local(monkeypatch):
    def fail_cloud(*args, **kwargs):
        raise RuntimeError("cloud unavailable")

    monkeypatch.setattr("backend.app.text_polish.polish_transcript_with_provider", fail_cloud)

    text, segments = polish_transcript(
        "Спикер 1:\nНужен эй пи ай.",
        [{"start": 0.0, "end": 1.0, "text": "Нужен эй пи ай.", "speaker": "Спикер 1"}],
        TextPolishConfig(provider="openai", openai_api_key="test-key"),
    )

    assert segments[0]["text"] == "Нужен API."
    assert "API" in text


def test_text_polish_provider_chain_uses_priority_and_available_keys(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("QWEN_API_KEY", "qwen-key")

    chain = build_provider_chain(
        TextPolishConfig(provider="auto", providers=("openai", "deepseek", "qwen"), openai_api_key=None)
    )

    assert [spec.name for spec in chain] == ["deepseek", "qwen"]
    assert chain[0].model == "deepseek-chat"


def test_text_polish_provider_aliases(monkeypatch):
    monkeypatch.setenv("GIGACHAT_ACCESS_TOKEN", "giga-token")
    monkeypatch.setenv("XAI_API_KEY", "xai-key")

    chain = build_provider_chain(TextPolishConfig(provider="auto", providers=("gigachad", "xai")))

    assert [spec.name for spec in chain] == ["gigachat", "grok"]


def test_parse_polish_replacements_accepts_markdown_json_block():
    replacements = parse_polish_replacements(
        '```json\n{"segments":[{"index":0,"text":"Нужен эй пи ай."}]}\n```'
    )

    assert replacements == {0: "Нужен API."}
