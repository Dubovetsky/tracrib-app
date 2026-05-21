from backend.app.text_polish import apply_segment_replacements
from backend.app.postprocess import normalize_domain_terms


def test_cloud_replacement_can_assign_generic_speaker_when_acoustic_label_is_missing():
    segments = [{"start": 0.0, "end": 1.0, "text": "Начнем встречу."}]

    polished = apply_segment_replacements(
        segments,
        {0: {"speaker": "Спикер 15", "text": "Начнем встречу."}},
    )

    assert polished[0]["speaker"] == "Спикер 15"
    assert polished[0]["text"] == "Начнем встречу."


def test_jira_is_normalized_without_free_text_rewrite():
    assert normalize_domain_terms("Нужно завести задачу в джире.") == "Нужно завести задачу в Jira."

    segments = [{"start": 0.0, "end": 1.0, "text": "Нужно завести задачу в джире."}]
    polished = apply_segment_replacements(
        segments,
        {0: {"speaker": "Спикер 1", "text": "Нужно срочно завести задачу в Jira."}},
    )

    assert polished[0]["text"] == "Нужно завести задачу в Jira."
