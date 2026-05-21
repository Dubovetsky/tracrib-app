from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

import backend.app.main as main_module
import backend.app.services as services_module
from backend.app.services import JobService
from backend.app.settings import Settings
from backend.app.transcriber import TranscriptionResult


class FakeTranscriber:
    def transcribe(self, audio_path: Path, language: str = "ru") -> TranscriptionResult:
        return TranscriptionResult(
            text="Smoke transcript.",
            segments=[{"start": 0.0, "end": 1.0, "text": "Smoke transcript.", "speaker": "Speaker 1"}],
            diarization_status="succeeded",
            raw_speaker_count=1,
            speaker_count=1,
            timings={"asr_seconds": 0.01, "diarization_seconds": 0.01},
        )


def test_upload_poll_and_download_smoke(tmp_path, monkeypatch):
    def fake_preprocess_audio(source_path: Path, wav_path: Path) -> None:
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path.write_bytes(b"fake wav")

    settings = Settings(data_dir=tmp_path, text_polish_provider="local", diarization_enabled=False)
    service = JobService(settings)
    service.transcriber = FakeTranscriber()

    monkeypatch.setattr(services_module, "preprocess_audio", fake_preprocess_audio)
    monkeypatch.setattr(main_module, "service", service)

    with TestClient(main_module.app) as client:
        response = client.post(
            "/api/upload",
            data={"expected_speakers": "3"},
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
        assert job["expected_speaker_count"] == 3
        assert job["diarization_status"] == "succeeded"
        assert job["raw_speaker_count"] == 1
        assert job["speaker_count"] == 1
        assert job["timings"]["asr_seconds"] == 0.01

        result_response = client.get(f"/api/jobs/{job_id}/result")
        assert result_response.status_code == 200
        assert "Smoke transcript." in result_response.text

        for format_name in ("txt", "srt", "vtt", "diagnostics", "diarization-turns", "segments"):
            download_response = client.get(f"/api/jobs/{job_id}/download/{format_name}")
            assert download_response.status_code == 200
            assert download_response.content
