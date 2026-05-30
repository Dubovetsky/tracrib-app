from backend.app.exports import write_exports


def test_write_exports_only_writes_main_txt(tmp_path):
    paths = write_exports(
        "РџСЂРёРІРµС‚ РјРёСЂ",
        [{"start": 0.0, "end": 1.0, "text": "РџСЂРёРІРµС‚ РјРёСЂ"}],
        tmp_path,
    )

    assert set(paths) == {"txt"}
    assert paths["txt"].read_text(encoding="utf-8") == "РџСЂРёРІРµС‚ РјРёСЂ\n"
    assert not (tmp_path / "transcript.srt").exists()
    assert not (tmp_path / "transcript.vtt").exists()
