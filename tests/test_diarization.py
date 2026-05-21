from backend.app.diarization import (
    DiarizationConfig,
    PyannoteDiarizationEngine,
    SpeakerTurn,
    annotation_from_pyannote_output,
    apply_diarization,
    best_speaker_for_segment,
    load_audio_for_pyannote,
    overlap_seconds,
)
from backend.app.postprocess import postprocess_transcript


def test_overlap_seconds_returns_shared_duration_only():
    assert overlap_seconds(1.0, 4.0, 2.0, 5.0) == 2.0
    assert overlap_seconds(1.0, 2.0, 2.0, 3.0) == 0.0


def test_best_speaker_for_segment_uses_largest_overlap():
    segment = {"start": 10.0, "end": 16.0, "text": "Текст"}
    turns = [
        SpeakerTurn(9.0, 11.0, "SPEAKER_00"),
        SpeakerTurn(11.0, 16.0, "SPEAKER_01"),
    ]

    assert best_speaker_for_segment(segment, turns) == "SPEAKER_01"


def test_pyannote_diarization_prefers_exact_expected_speaker_count(monkeypatch):
    captured_kwargs = {}

    class FakeAnnotation:
        def itertracks(self, yield_label: bool = False):
            return iter([])

    class FakePipeline:
        def __call__(self, audio, **kwargs):
            captured_kwargs.update(kwargs)
            return FakeAnnotation()

    monkeypatch.setattr(PyannoteDiarizationEngine, "_load_pipeline", lambda self: FakePipeline())
    monkeypatch.setattr(
        "backend.app.diarization.load_audio_for_pyannote",
        lambda audio_path: {"waveform": object(), "sample_rate": 16000},
    )

    engine = PyannoteDiarizationEngine(DiarizationConfig(min_speakers=2, max_speakers=4))
    engine.diarize(__import__("pathlib").Path("sample.wav"), expected_speakers=3)

    assert captured_kwargs == {"num_speakers": 3}


def test_pyannote_diarization_reads_current_diarize_output_shape(monkeypatch):
    class FakeTurn:
        start = 1.0
        end = 2.0

    class FakeAnnotation:
        def itertracks(self, yield_label: bool = False):
            return iter([(FakeTurn(), None, "SPEAKER_02")])

    class FakeDiarizeOutput:
        speaker_diarization = object()
        exclusive_speaker_diarization = FakeAnnotation()

    assert annotation_from_pyannote_output(FakeDiarizeOutput()).itertracks

    class FakePipeline:
        def __call__(self, audio, **kwargs):
            return FakeDiarizeOutput()

    monkeypatch.setattr(PyannoteDiarizationEngine, "_load_pipeline", lambda self: FakePipeline())
    monkeypatch.setattr(
        "backend.app.diarization.load_audio_for_pyannote",
        lambda audio_path: {"waveform": object(), "sample_rate": 16000},
    )

    engine = PyannoteDiarizationEngine(DiarizationConfig())

    assert engine.diarize(__import__("pathlib").Path("sample.wav")) == [
        SpeakerTurn(1.0, 2.0, "SPEAKER_02")
    ]


def test_apply_diarization_maps_raw_labels_to_numbered_speakers():
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Первый сегмент."},
        {"start": 2.0, "end": 4.0, "text": "Второй сегмент."},
        {"start": 4.0, "end": 6.0, "text": "Третий сегмент."},
    ]
    turns = [
        SpeakerTurn(0.0, 2.2, "SPEAKER_10"),
        SpeakerTurn(2.2, 6.0, "SPEAKER_20"),
    ]

    diarized = apply_diarization(segments, turns)

    assert diarized[0]["speaker"] == "Спикер 1"
    assert diarized[1]["speaker"] == "Спикер 2"
    assert diarized[2]["speaker"] == "Спикер 2"

def test_apply_diarization_splits_single_asr_segment_by_word_timestamps():
    segments = [
        {
            "start": 0.0,
            "end": 4.0,
            "text": "РџРµСЂРІС‹Р№ РѕС‚РІРµС‡Р°РµС‚ РІС‚РѕСЂРѕР№.",
            "words": [
                {"start": 0.0, "end": 0.8, "word": "РџРµСЂРІС‹Р№"},
                {"start": 0.8, "end": 1.6, "word": "РѕС‚РІРµС‡Р°РµС‚"},
                {"start": 2.2, "end": 3.0, "word": "РІС‚РѕСЂРѕР№."},
            ],
        }
    ]
    turns = [
        SpeakerTurn(0.0, 2.0, "SPEAKER_00"),
        SpeakerTurn(2.0, 4.0, "SPEAKER_01"),
    ]

    diarized = apply_diarization(segments, turns)

    assert len(diarized) == 2
    assert diarized[0]["speaker"].endswith("1")
    assert diarized[0]["raw_speaker"] == "SPEAKER_00"
    assert diarized[0]["text"] == "РџРµСЂРІС‹Р№ РѕС‚РІРµС‡Р°РµС‚"
    assert diarized[1]["speaker"].endswith("2")
    assert diarized[1]["raw_speaker"] == "SPEAKER_01"
    assert diarized[1]["text"] == "РІС‚РѕСЂРѕР№."


def test_postprocess_preserves_diarized_speakers():
    text, segments = postprocess_transcript(
        [
            {"start": 0.0, "end": 1.0, "text": "Первый говорит.", "speaker": "Спикер 1"},
            {"start": 1.0, "end": 2.0, "text": "Второй отвечает.", "speaker": "Спикер 2"},
        ]
    )

    assert segments[0]["speaker"] == "Спикер 1"
    assert segments[1]["speaker"] == "Спикер 2"
    assert "Спикер 1:" in text
    assert "Спикер 2:" in text


def test_postprocess_reuses_name_for_diarized_speaker_after_intro():
    _, segments = postprocess_transcript(
        [
            {"start": 0.0, "end": 1.0, "text": "Наталья: Начнем встречу.", "speaker": "Спикер 1"},
            {"start": 1.0, "end": 2.0, "text": "Переходим к плану.", "speaker": "Спикер 1"},
        ]
    )

    assert segments[0]["speaker"] == "Наталья"
    assert segments[1]["speaker"] == "Наталья"
