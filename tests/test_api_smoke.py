from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

import backend.app.main as main_module
import backend.app.services as services_module
from backend.app.services import JobService, auto_audio_profile_for_quality
from backend.app.services import estimate_stage_remaining_floor
from backend.app.settings import Settings
from backend.app.transcriber import TranscriptionResult


class FakeTranscriber:
    def transcribe(
        self,
        audio_path: Path,
        language: str = "ru",
        expected_speakers: int | None = None,
        asr_quality: str = "balanced",
        participant_names: str = "",
        custom_vocabulary: str = "",
        source_duration_seconds: object = None,
        progress_callback=None,
    ) -> TranscriptionResult:
        if progress_callback:
            progress_callback("asr", 50.0, "Распознаем речь")
        return TranscriptionResult(
            text="Smoke transcript.",
            segments=[{"start": 0.0, "end": 1.0, "text": "Smoke transcript.", "speaker": "Speaker 1"}],
            raw_text="Smoke transcript.",
            raw_segments=[{"start": 0.0, "end": 1.0, "text": "Smoke transcript."}],
            diarization_status="succeeded",
            raw_speaker_count=1,
            speaker_count=1,
            timings={"asr_seconds": 0.01, "diarization_seconds": 0.01},
        )


def test_upload_poll_and_download_smoke(tmp_path, monkeypatch):
    def fake_preprocess_audio(source_path: Path, wav_path: Path, profile: str = "speech") -> dict[str, object]:
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path.write_bytes(b"fake wav")
        return {"audio_profile": profile, "sample_rate": 16000, "channels": 1}

    settings = Settings(data_dir=tmp_path, text_polish_provider="local", diarization_enabled=False)
    service = JobService(settings)
    service.transcriber = FakeTranscriber()

    monkeypatch.setattr(services_module, "preprocess_audio", fake_preprocess_audio)
    monkeypatch.setattr(main_module, "service", service)

    with TestClient(main_module.app) as client:
        response = client.post(
            "/api/upload",
            files={"file": ("sample.m4a", b"fake audio", "audio/mp4")},
        )
        assert response.status_code == 201
        job_id = response.json()["id"]

        job = None
        for _ in range(20):
            job_response = client.get(f"/api/jobs/{job_id}")
            assert job_response.status_code == 200
            job = job_response.json()
            if job["status"] == "completed":
                break
            time.sleep(0.05)

        assert job is not None
        assert job["status"] == "completed"
        assert job["expected_speaker_count"] is None
        assert job["asr_quality"] == "balanced"
        assert job["audio_profile"] == "speech"
        assert job["processing_stage"] == "completed"
        assert job["progress_percent"] == 100.0
        assert job["progress_message"] == "Готово"
        assert job["diarization_status"] == "succeeded"
        assert job["raw_speaker_count"] == 1
        assert job["speaker_count"] == 1
        assert job["timings"]["asr_seconds"] == 0.01

        result_response = client.get(f"/api/jobs/{job_id}/result")
        assert result_response.status_code == 200
        assert "Smoke transcript." in result_response.text

        for format_name in (
            "txt",
            "raw-txt",
        ):
            download_response = client.get(f"/api/jobs/{job_id}/download/{format_name}")
            assert download_response.status_code == 200
            assert download_response.content


def test_raw_download_falls_back_for_legacy_jobs(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, text_polish_provider="off", diarization_enabled=False)
    service = JobService(settings)
    result_dir = tmp_path / "results" / "legacy-job"
    result_dir.mkdir(parents=True)
    text_path = result_dir / "transcript.txt"
    text_path.write_text("Legacy transcript\n", encoding="utf-8")
    service.db.create_job(
        {
            "id": "legacy-job",
            "original_filename": "legacy.m4a",
            "stored_audio_path": str(tmp_path / "legacy.m4a"),
            "status": "completed",
        }
    )
    service.db.update_job(
        "legacy-job",
        status="completed",
        text_path=str(text_path),
    )
    monkeypatch.setattr(main_module, "service", service)

    with TestClient(main_module.app) as client:
        raw_text_response = client.get("/api/jobs/legacy-job/download/raw-txt")

    assert raw_text_response.status_code == 200
    assert raw_text_response.text.replace("\r\n", "\n") == "Legacy transcript\n"


def test_delete_job_removes_history_entry(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, text_polish_provider="off", diarization_enabled=False)
    service = JobService(settings)
    stored_path = tmp_path / "uploads" / "delete-job.m4a"
    stored_path.parent.mkdir(parents=True)
    stored_path.write_bytes(b"audio")
    service.db.create_job(
        {
            "id": "delete-job",
            "original_filename": "delete.m4a",
            "stored_audio_path": str(stored_path),
            "status": "completed",
        }
    )
    monkeypatch.setattr(main_module, "service", service)

    with TestClient(main_module.app) as client:
        response = client.delete("/api/jobs/delete-job")
        missing = client.get("/api/jobs/delete-job")

    assert response.status_code == 204
    assert missing.status_code == 404
    assert not stored_path.exists()


def test_cancel_job_marks_pending_job_as_failed(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, text_polish_provider="off", diarization_enabled=False)
    service = JobService(settings)
    monkeypatch.setattr(main_module, "service", service)

    with TestClient(main_module.app) as client:
        service.db.create_job(
            {
                "id": "cancel-job",
                "original_filename": "cancel.m4a",
                "stored_audio_path": str(tmp_path / "cancel.m4a"),
                "status": "queued",
            }
        )
        response = client.post("/api/jobs/cancel-job/cancel")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["processing_stage"] == "cancelled"
    assert payload["progress_message"] == "Обработка прервана"
    assert payload["error"] == "Processing was cancelled by user."


def test_diarization_readiness_reports_missing_token(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, diarization_enabled=True, diarization_auth_token=None)
    service = JobService(settings)
    service.diarization_engine = type(
        "BrokenDiarization",
        (),
        {"_load_pipeline": lambda self: (_ for _ in ()).throw(RuntimeError("missing gated access"))},
    )()
    monkeypatch.setattr(main_module, "service", service)

    with TestClient(main_module.app) as client:
        response = client.get("/api/diarization/readiness")

    assert response.status_code == 200
    readiness = response.json()
    assert readiness["enabled"] is True
    assert readiness["token_configured"] is False
    assert readiness["cache_writable"] is True
    assert readiness["ready"] is False


def test_upload_accepts_auto_speaker_count(tmp_path, monkeypatch):
    service = JobService(Settings(data_dir=tmp_path, diarization_enabled=False))
    monkeypatch.setattr(main_module, "service", service)

    with TestClient(main_module.app) as client:
        response = client.post(
            "/api/upload",
            files={"file": ("sample.m4a", b"fake audio", "audio/mp4")},
        )

    assert response.status_code == 201
    assert response.json()["expected_speaker_count"] is None


def test_upload_allows_expected_speakers_up_to_twenty(tmp_path, monkeypatch):
    service = JobService(Settings(data_dir=tmp_path, diarization_enabled=False))
    monkeypatch.setattr(main_module, "service", service)

    with TestClient(main_module.app) as client:
        response = client.post(
            "/api/upload",
            data={"expected_speakers": "15"},
            files={"file": ("sample.m4a", b"fake audio", "audio/mp4")},
        )

    assert response.status_code == 201
    assert response.json()["expected_speaker_count"] == 15


def test_audio_profile_is_automatic_by_asr_quality():
    assert auto_audio_profile_for_quality("accurate") == "speech"
    assert auto_audio_profile_for_quality("balanced") == "speech"
    assert auto_audio_profile_for_quality("fast") == "conservative"


def test_asr_progress_reserves_time_for_remaining_phases():
    remaining = estimate_stage_remaining_floor(
        stage="asr",
        progress=66.0,
        baseline_estimate=3600.0,
        elapsed=240.0,
    )

    assert remaining >= 1200.0


def test_diarization_progress_never_reports_seconds_left():
    remaining = estimate_stage_remaining_floor(
        stage="diarization",
        progress=70.0,
        baseline_estimate=3600.0,
        elapsed=240.0,
    )

    assert remaining >= 720.0


def test_asr_progress_is_only_early_pipeline_slice(tmp_path):
    service = JobService(Settings(data_dir=tmp_path, diarization_enabled=False))
    service.db.create_job(
        {
            "id": "progress-job",
            "original_filename": "sample.m4a",
            "stored_audio_path": str(tmp_path / "sample.m4a"),
            "status": "processing",
            "source_duration_seconds": 3600.0,
            "asr_quality": "balanced",
            "audio_profile": "speech",
        }
    )

    service.update_processing_progress("progress-job", "asr", 30.0, "Распознаем речь", 1.0)

    job = service.db.get_job("progress-job")
    assert job is not None
    assert job["progress_percent"] == 30.0
    assert job["estimated_total_seconds"] > 600.0
