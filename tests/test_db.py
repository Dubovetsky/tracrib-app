from backend.app.db import Database


def test_database_persists_jobs(tmp_path):
    db_path = tmp_path / "jobs.sqlite3"
    db = Database(db_path)
    db.create_job(
        {
            "id": "job-1",
            "original_filename": "audio.m4a",
            "stored_audio_path": str(tmp_path / "audio.m4a"),
        }
    )
    db.update_job("job-1", status="completed", text_path=str(tmp_path / "result.txt"))

    reopened = Database(db_path)
    job = reopened.get_job("job-1")

    assert job is not None
    assert job["status"] == "completed"
    assert job["language"] == "ru"
    assert job["text_path"].endswith("result.txt")


def test_database_lists_jobs_by_status(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    db.create_job(
        {
            "id": "job-1",
            "original_filename": "first.wav",
            "stored_audio_path": str(tmp_path / "first.wav"),
            "status": "queued",
        }
    )
    db.create_job(
        {
            "id": "job-2",
            "original_filename": "second.wav",
            "stored_audio_path": str(tmp_path / "second.wav"),
            "status": "failed",
        }
    )

    queued = db.list_jobs_by_status("queued")

    assert [job["id"] for job in queued] == ["job-1"]


def test_database_persists_operability_metadata(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    db.create_job(
        {
            "id": "job-1",
            "original_filename": "audio.m4a",
            "stored_audio_path": str(tmp_path / "audio.m4a"),
            "expected_speaker_count": 3,
            "asr_quality": "accurate",
            "audio_profile": "speech",
            "participant_names": "Наталья, Антон",
            "custom_vocabulary": "EADR, Jira",
        }
    )
    db.update_job(
        "job-1",
        status="completed",
        diarization_status="succeeded",
        raw_speaker_count=3,
        speaker_count=2,
        warnings_json='["low confidence"]',
        timings_json='{"asr_seconds": 1.25}',
    )

    job = Database(tmp_path / "jobs.sqlite3").get_job("job-1")

    assert job["diarization_status"] == "succeeded"
    assert job["expected_speaker_count"] == 3
    assert job["asr_quality"] == "accurate"
    assert job["audio_profile"] == "speech"
    assert job["participant_names"] == "Наталья, Антон"
    assert job["custom_vocabulary"] == "EADR, Jira"
    assert job["raw_speaker_count"] == 3
    assert job["speaker_count"] == 2
    assert job["warnings_json"] == '["low confidence"]'
    assert job["timings_json"] == '{"asr_seconds": 1.25}'
