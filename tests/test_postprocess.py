from backend.app.exports import render_srt, render_vtt
from backend.app.postprocess import (
    normalize_domain_terms,
    postprocess_transcript,
    split_paragraphs,
    split_sentences,
)


def test_postprocess_uses_explicit_speaker_names():
    text, segments = postprocess_transcript(
        [
            {"start": 0.0, "end": 1.0, "text": "Наталья: Добрый день. Начнем встречу."},
            {"start": 1.2, "end": 2.0, "text": "Андрей: Да, я готов."},
        ]
    )

    assert segments[0]["speaker"] == "Наталья"
    assert segments[0]["text"] == "Добрый день. Начнем встречу."
    assert segments[1]["speaker"] == "Андрей"
    assert "Наталья:\nДобрый день. Начнем встречу." in text
    assert "Андрей:\nДа, я готов." in text


def test_postprocess_falls_back_to_numbered_speakers():
    text, segments = postprocess_transcript(
        [
            {"start": 0.0, "end": 1.0, "text": "Что обсудим?"},
            {"start": 1.5, "end": 2.0, "text": "План проекта."},
        ]
    )

    assert segments[0]["speaker"] == "Спикер 1"
    assert segments[1]["speaker"] == "Спикер 2"
    assert "Спикер 1:" in text
    assert "Спикер 2:" in text


def test_split_sentences_and_paragraphs_for_readability():
    sentences = split_sentences("Первое предложение. Второе предложение? Третье предложение!")
    paragraphs = split_paragraphs(
        "Первое предложение. Второе предложение? Третье предложение! Четвертое предложение."
    )

    assert sentences == ["Первое предложение.", "Второе предложение?", "Третье предложение!"]
    assert paragraphs == [
        "Первое предложение. Второе предложение? Третье предложение!",
        "Четвертое предложение.",
    ]


def test_subtitle_exports_include_speaker_when_present():
    segments = [{"start": 0.0, "end": 2.5, "text": "Привет", "speaker": "Наталья"}]

    assert "Наталья: Привет" in render_srt(segments)
    assert "Наталья: Привет" in render_vtt(segments)


def test_postprocess_removes_trailing_subtitle_artifacts():
    text, segments = postprocess_transcript(
        [
            {"start": 0.0, "end": 2.0, "text": "Обсудили sprint review и backlog."},
            {"start": 2.1, "end": 3.0, "text": "Субтитры сделал DimaTorzok"},
        ]
    )

    assert len(segments) == 1
    assert "Субтитры" not in text
    assert "DimaTorzok" not in text
    assert "Обсудили sprint review и backlog." in text


def test_postprocess_strips_trailing_artifact_from_last_useful_segment():
    text, segments = postprocess_transcript(
        [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "Фиксируем API контракт. Субтитры сделал DimaTorzok",
            },
        ]
    )

    assert segments[0]["text"] == "Фиксируем API контракт."
    assert "Субтитры" not in text


def test_postprocess_normalizes_it_and_agile_abbreviations():
    text, segments = postprocess_transcript(
        [
            {
                "start": 0.0,
                "end": 4.0,
                "text": "Проверим эй пи ай, ю ай, эм ви пи, си ай си ди и ди о ди перед sprint review.",
            },
        ]
    )

    assert segments[0]["text"] == "Проверим API, UI, MVP, CI/CD и DoD перед sprint review."
    assert "API, UI, MVP, CI/CD и DoD" in text


def test_postprocess_normalizes_common_spoken_it_abbreviations():
    assert normalize_domain_terms(
        "эйч ти ти пи эс API, эс кью эл база, джей сон, джей эс, ти эс и си эс эс"
    ) == "HTTPS API, SQL база, JSON, JS, TS и CSS"


def test_postprocess_prefers_longer_spoken_abbreviations():
    assert normalize_domain_terms(
        "настроим си ди эн, эс эль эй, эс эль о, эс эль ай и эс эс эйч доступ"
    ) == "настроим CDN, SLA, SLO, SLI и SSH доступ"


def test_postprocess_normalizes_ai_and_data_abbreviations():
    assert normalize_domain_terms(
        "проверим эй ай, эм эл, эл эл эм, эн эл пи, о си ар, эй эс ар и и ти эл"
    ) == "проверим AI, ML, LLM, NLP, OCR, ASR и ETL"


def test_split_sentences_keeps_dotted_english_abbreviations():
    sentences = split_sentences("A. P. I. контракт готов. Следующий шаг QA.")

    assert sentences == ["A. P. I. контракт готов.", "Следующий шаг QA."]


def test_normalize_domain_terms_keeps_known_acronyms_uppercase():
    assert normalize_domain_terms("api, ui, ux, mvp, qa, okrs, kpis, wip и ci/cd") == (
        "API, UI, UX, MVP, QA, OKR, KPI, WIP и CI/CD"
    )
