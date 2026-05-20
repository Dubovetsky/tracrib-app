from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from .audio import preprocess_audio
from .db import Database, utc_now
from .diarization import DiarizationConfig, build_diarization_engine
from .exports import write_exports
from .settings import Settings
from .text_polish import TextPolishConfig, polish_transcript
from .transcriber import FasterWhisperEngine


class JobService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings.db_path)
        self.diarization_engine = build_diarization_engine(
            DiarizationConfig(
                enabled=settings.diarization_enabled,
                model_name=settings.diarization_model,
                device=settings.diarization_device,
                min_speakers=settings.diarization_min_speakers,
                max_speakers=settings.diarization_max_speakers,
                auth_token=settings.diarization_auth_token,
            )
        )
        self.transcriber = FasterWhisperEngine(
            model_name=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            fallback_compute_type=settings.whisper_fallback_compute_type,
            diarization_engine=self.diarization_engine,
        )
        self.queue: asyncio.Queue[str] | None = None
        self.worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self.queue is None:
            self.queue = asyncio.Queue()
        for job in self.db.list_jobs_by_status("processing"):
            self.db.update_job(
                job["id"],
                status="failed",
                error="Processing was interrupted by application restart.",
                finished_at=utc_now(),
            )
        for job in self.db.list_jobs_by_status("queued"):
            await self.queue.put(job["id"])
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

    async def create_upload_job(self, upload: UploadFile) -> dict:
        job_id = str(uuid.uuid4())
        original_name = Path(upload.filename or "audio").name
        suffix = Path(original_name).suffix
        stored_path = self.settings.upload_dir / f"{job_id}{suffix}"
        stored_path.parent.mkdir(parents=True, exist_ok=True)
        with stored_path.open("wb") as target:
            shutil.copyfileobj(upload.file, target)

        self.db.create_job(
            {
                "id": job_id,
                "original_filename": original_name,
                "stored_audio_path": str(stored_path),
                "language": self.settings.language,
                "status": "queued",
            }
        )
        await self.enqueue(job_id)
        return self.get_job(job_id)

    async def enqueue(self, job_id: str) -> None:
        if self.queue is None:
            self.queue = asyncio.Queue()
        await self.queue.put(job_id)

    def get_job(self, job_id: str) -> dict | None:
        return self.db.get_job(job_id)

    def list_jobs(self) -> list[dict]:
        return self.db.list_jobs()

    async def _worker(self) -> None:
        assert self.queue is not None
        while True:
            job_id = await self.queue.get()
            try:
                await asyncio.to_thread(self.process_job, job_id)
            finally:
                self.queue.task_done()

    def process_job(self, job_id: str) -> None:
        job = self.db.get_job(job_id)
        if not job:
            return

        self.db.update_job(
            job_id,
            status="processing",
            started_at=utc_now(),
            error=None,
        )
        try:
            wav_path = self.settings.wav_dir / f"{job_id}.wav"
            preprocess_audio(Path(job["stored_audio_path"]), wav_path)
            text, segments = self.transcriber.transcribe(wav_path, language=self.settings.language)
            text, segments = polish_transcript(
                text,
                segments,
                TextPolishConfig(
                    provider=self.settings.text_polish_provider,
                    providers=self.settings.text_polish_providers,
                    model=self.settings.text_polish_model,
                    timeout_seconds=self.settings.text_polish_timeout_seconds,
                    openai_api_key=self.settings.openai_api_key,
                ),
                language=self.settings.language,
            )
            export_paths = write_exports(text, segments, self.settings.result_dir / job_id)
            self.db.update_job(
                job_id,
                status="completed",
                preprocessed_audio_path=str(wav_path),
                text_path=str(export_paths["txt"]),
                srt_path=str(export_paths["srt"]),
                vtt_path=str(export_paths["vtt"]),
                finished_at=utc_now(),
            )
        except Exception as exc:
            self.db.update_job(
                job_id,
                status="failed",
                error=str(exc),
                finished_at=utc_now(),
            )
