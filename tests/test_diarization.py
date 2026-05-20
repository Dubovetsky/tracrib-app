from backend.app.diarization import SpeakerTurn, apply_diarization, best_speaker_for_segment, overlap_seconds
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
