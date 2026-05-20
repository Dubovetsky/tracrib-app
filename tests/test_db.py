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
