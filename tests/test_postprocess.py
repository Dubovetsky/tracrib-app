from backend.app.exports import render_srt, render_vtt
from backend.app.postprocess import postprocess_transcript, split_paragraphs, split_sentences


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
