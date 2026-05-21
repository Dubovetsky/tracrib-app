from backend.app.postprocess import postprocess_transcript


def test_postprocess_can_preserve_asr_words_for_verbatim_output():
    text, segments = postprocess_transcript(
        [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "Speaker: Check эй пи ай.",
                "speaker": "Speaker 1",
            },
        ],
        preserve_words=True,
    )

    assert segments[0]["speaker"] == "Speaker"
    assert segments[0]["text"] == "Speaker: Check эй пи ай."
    assert "эй пи ай" in text
