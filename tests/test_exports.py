from backend.app.exports import format_srt_timestamp, render_srt, render_vtt, write_exports


def test_timestamp_formatting():
    assert format_srt_timestamp(3723.456) == "01:02:03,456"


def test_render_subtitle_exports():
    segments = [{"start": 0.0, "end": 2.5, "text": "Привет"}]

    assert "00:00:00,000 --> 00:00:02,500" in render_srt(segments)
    assert render_vtt(segments).startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:02.500" in render_vtt(segments)


def test_write_exports(tmp_path):
    paths = write_exports(
        "Привет мир",
        [{"start": 0.0, "end": 1.0, "text": "Привет мир"}],
        tmp_path,
    )

    assert paths["txt"].read_text(encoding="utf-8") == "Привет мир\n"
    assert paths["srt"].exists()
    assert paths["vtt"].exists()
