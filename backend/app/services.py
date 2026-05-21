from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
import traceback
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import UploadFile

from .audio import preprocess_audio, probe_audio
from .db import Database, utc_now
from .diarization import DiarizationConfig, build_diarization_engine
from .exports import write_exports
from .hf_env import cache_is_writable, configure_huggingface_cache
from .performance import estimate_total_seconds, performance_summary
from .settings import Settings
from .text_polish import TextPolishConfig, polish_transcript
from .transcriber import FasterWhisperEngine


LOGGER = logging.getLogger("transcrib_app.backend")


class JobCancelled(RuntimeError):
    pass


def configure_backend_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    if any(isinstance(handler, RotatingFileHandler) for handler in LOGGER.handlers):
        return
    handler = RotatingFileHandler(
        log_dir / "backend.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = True


class JobService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.hf_cache_dir = configure_huggingface_cache(settings.data_dir)
        configure_backend_logging(settings.log_dir)
        self.db = Database(settings.db_path)
        self.diarization_engine = build_diarization_engine(
            DiarizationConfig(
                enabled=settings.diarization_enabled,
                model_name=settings.diarization_model,
                device=settings.diarization_device,
                num_speakers=settings.diarization_num_speakers,
                min_speakers=settings.diarization_min_speakers,
                max_speakers=settings.diarization_max_speakers,
                auth_token=settings.diarization_auth_token,
            )
        )
        self.transcriber = FasterWhisperEngine(
            model_name=settings.whisper_model,
            accurate_model_name=settings.whisper_accurate_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            fallback_compute_type=settings.whisper_fallback_compute_type,
            diarization_engine=self.diarization_engine,
            initial_prompt=settings.whisper_initial_prompt,
            hotwords=settings.whisper_hotwords,
            preserve_asr_words=settings.preserve_asr_words,
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

    async def create_upload_job(
        self,
        upload: UploadFile,
        expected_speakers: int | None = None,
        asr_quality: str | None = None,
        audio_profile: str | None = None,
        participant_names: str | None = None,
        custom_vocabulary: str | None = None,
    ) -> dict:
        job_id = str(uuid.uuid4())
        original_name = Path(upload.filename or "audio").name
        suffix = Path(original_name).suffix
        stored_path = self.settings.upload_dir / f"{job_id}{suffix}"
        stored_path.parent.mkdir(parents=True, exist_ok=True)
        with stored_path.open("wb") as target:
            shutil.copyfileobj(upload.file, target)
        selected_quality = normalize_choice(asr_quality, self.settings.asr_quality, {"fast", "balanced", "accurate"})
        selected_profile = auto_audio_profile_for_quality(selected_quality, audio_profile, self.settings.audio_profile)
        source_duration_seconds = probe_audio(stored_path).get("duration_seconds")
        estimated_total_seconds = estimate_total_seconds(
            source_duration_seconds,
            selected_quality,
            selected_profile,
            jobs=self.db.list_jobs(),
        )

        self.db.create_job(
            {
                "id": job_id,
                "original_filename": original_name,
                "stored_audio_path": str(stored_path),
                "language": self.settings.language,
                "status": "queued",
                "expected_speaker_count": expected_speakers,
                "asr_quality": selected_quality,
                "audio_profile": selected_profile,
                "participant_names": normalize_text_metadata(participant_names),
                "custom_vocabulary": normalize_text_metadata(custom_vocabulary),
                "source_duration_seconds": source_duration_seconds,
                "estimated_total_seconds": estimated_total_seconds,
                "processing_stage": "queued",
                "progress_percent": 0.0,
                "progress_message": "Ожидает начала обработки",
            }
        )
        await self.enqueue(job_id)
        return self.get_job(job_id)

    async def enqueue(self, job_id: str) -> None:
        if self.queue is None:
            self.queue = asyncio.Queue()
        await self.queue.put(job_id)

    def get_job(self, job_id: str) -> dict | None:
        job = self.db.get_job(job_id)
        return normalize_job(job) if job else None

    def list_jobs(self) -> list[dict]:
        return [normalize_job(job) for job in self.db.list_jobs()]

    def delete_job(self, job_id: str) -> bool:
        job = self.db.get_job(job_id)
        if not job:
            return False
        self.db.delete_job(job_id)
        for field in (
            "stored_audio_path",
            "preprocessed_audio_path",
            "raw_text_path",
            "text_path",
            "srt_path",
            "vtt_path",
            "diarization_turns_path",
            "segments_json_path",
            "diagnostics_json_path",
        ):
            remove_path_if_inside_data(job.get(field), self.settings.data_dir)
        remove_path_if_inside_data(self.settings.result_dir / job_id, self.settings.data_dir)
        return True

    def cancel_job(self, job_id: str) -> bool:
        job = self.db.get_job(job_id)
        if not job:
            return False
        if job.get("status") not in {"queued", "processing"}:
            return True
        self.db.update_job(
            job_id,
            status="failed",
            cancel_requested=1,
            processing_stage="cancelled",
            progress_message="Обработка прервана",
            error="Processing was cancelled by user.",
            finished_at=utc_now(),
        )
        LOGGER.info("Job %s cancellation requested", job_id)
        return True

    def diarization_readiness(self) -> dict[str, object]:
        token_configured = bool(self.settings.diarization_auth_token)
        cache_writable = cache_is_writable(self.hf_cache_dir)
        pipeline_loadable = False
        pipeline_error = ""
        if self.diarization_engine is not None:
            try:
                load_pipeline = getattr(self.diarization_engine, "_load_pipeline", None)
                if callable(load_pipeline):
                    load_pipeline()
                    pipeline_loadable = True
            except Exception as exc:
                pipeline_error = str(exc)
        return {
            "enabled": self.settings.diarization_enabled,
            "model": self.settings.diarization_model,
            "device": self.settings.diarization_device,
            "token_configured": token_configured,
            "pipeline_loadable": pipeline_loadable,
            "pipeline_error": pipeline_error,
            "cache_dir": str(self.hf_cache_dir),
            "cache_writable": cache_writable,
            "required_access": [
                "pyannote/speaker-diarization-3.1",
                "pyannote/segmentation-3.0",
            ],
            "ready": self.settings.diarization_enabled and cache_writable and (token_configured or pipeline_loadable),
        }

    def performance_profile(self) -> dict[str, object]:
        return performance_summary(self.db.list_jobs())

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
        if job.get("cancel_requested") or job.get("status") not in {"queued", "processing"}:
            return

        self.db.update_job(
            job_id,
            status="processing",
            processing_stage="starting",
            progress_percent=1.0,
            progress_message="Запускаем обработку",
            started_at=utc_now(),
            error=None,
        )
        try:
            total_started_at = time.perf_counter()
            timings: dict[str, float] = {}
            warnings: list[str] = []
            wav_path = self.settings.wav_dir / f"{job_id}.wav"
            phase_started_at = time.perf_counter()
            self.update_processing_progress(
                job_id,
                "preprocess",
                4.0,
                "Готовим аудио для распознавания",
                total_started_at,
            )
            audio_diagnostics = preprocess_audio(
                Path(job["stored_audio_path"]),
                wav_path,
                profile=job.get("audio_profile") or self.settings.audio_profile,
            )
            timings["preprocess_seconds"] = round(time.perf_counter() - phase_started_at, 3)
            if audio_diagnostics:
                warnings.append(f"Audio preprocess: {json.dumps(audio_diagnostics, ensure_ascii=False)}")
            self.ensure_not_cancelled(job_id)
            self.update_processing_progress(
                job_id,
                "asr",
                8.0,
                "Распознаем речь",
                total_started_at,
            )

            last_progress_update = 0.0

            def transcriber_progress(stage: str, progress_percent: float, message: str) -> None:
                nonlocal last_progress_update
                now = time.perf_counter()
                if progress_percent < 98 and now - last_progress_update < 2.0:
                    return
                last_progress_update = now
                self.update_processing_progress(
                    job_id,
                    stage,
                    progress_percent,
                    message,
                    total_started_at,
                )

            result = self.transcriber.transcribe(
                wav_path,
                language=self.settings.language,
                expected_speakers=job.get("expected_speaker_count"),
                asr_quality=job.get("asr_quality") or self.settings.asr_quality,
                participant_names=job.get("participant_names") or "",
                custom_vocabulary=job.get("custom_vocabulary") or "",
                source_duration_seconds=job.get("source_duration_seconds"),
                progress_callback=transcriber_progress,
            )
            self.ensure_not_cancelled(job_id)
            timings.update(result.timings)
            warnings.extend(result.warnings)
            warnings.extend(build_diarization_readiness_warnings(result, job))
            raw_paths = write_raw_asr_artifacts(
                self.settings.result_dir / job_id,
                result.raw_text,
            )
            self.ensure_not_cancelled(job_id)

            phase_started_at = time.perf_counter()
            self.update_processing_progress(
                job_id,
                "polish",
                92.0,
                "Собираем итоговый текст",
                total_started_at,
            )
            text, segments = polish_transcript(
                result.text,
                result.segments,
                TextPolishConfig(
                    provider=self.settings.text_polish_provider,
                    providers=self.settings.text_polish_providers,
                    model=self.settings.text_polish_model,
                    timeout_seconds=self.settings.text_polish_timeout_seconds,
                    openai_api_key=self.settings.openai_api_key,
                ),
                language=self.settings.language,
            )
            timings["text_polish_seconds"] = round(time.perf_counter() - phase_started_at, 3)
            self.ensure_not_cancelled(job_id)

            phase_started_at = time.perf_counter()
            self.update_processing_progress(
                job_id,
                "export",
                97.0,
                "Готовим файл для скачивания",
                total_started_at,
            )
            export_paths = write_exports(text, segments, self.settings.result_dir / job_id)
            timings["export_seconds"] = round(time.perf_counter() - phase_started_at, 3)
            timings["total_job_seconds"] = round(time.perf_counter() - total_started_at, 3)
            self.ensure_not_cancelled(job_id)
            self.db.update_job(
                job_id,
                status="completed",
                processing_stage="completed",
                progress_percent=100.0,
                progress_message="Готово",
                estimated_total_seconds=timings["total_job_seconds"],
                preprocessed_audio_path=str(wav_path),
                raw_text_path=str(raw_paths["raw_txt"]),
                raw_segments_json_path=None,
                text_path=str(export_paths["txt"]),
                srt_path=None,
                vtt_path=None,
                diarization_status=result.diarization_status,
                raw_speaker_count=result.raw_speaker_count,
                speaker_count=result.speaker_count,
                warnings_json=json.dumps(warnings, ensure_ascii=False),
                timings_json=json.dumps(timings, ensure_ascii=False),
                diarization_turns_path=None,
                segments_json_path=None,
                diagnostics_json_path=None,
                finished_at=utc_now(),
            )
        except JobCancelled:
            LOGGER.info("Job %s cancelled", job_id)
            self.db.update_job(
                job_id,
                status="failed",
                cancel_requested=1,
                processing_stage="cancelled",
                progress_message="Обработка прервана",
                error="Processing was cancelled by user.",
                finished_at=utc_now(),
            )
        except Exception as exc:
            traceback_text = traceback.format_exc()
            LOGGER.error("Job %s failed:\n%s", job_id, traceback_text)
            self.db.update_job(
                job_id,
                status="failed",
                processing_stage="failed",
                progress_message="Обработка завершилась ошибкой",
                error=build_readable_error(exc),
                finished_at=utc_now(),
            )

    def update_processing_progress(
        self,
        job_id: str,
        stage: str,
        progress_percent: float,
        message: str,
        started_at: float,
    ) -> None:
        self.ensure_not_cancelled(job_id)
        progress = max(1.0, min(99.0, progress_percent))
        elapsed = max(1.0, time.perf_counter() - started_at)
        fields: dict[str, object] = {
            "processing_stage": stage,
            "progress_percent": round(progress, 1),
            "progress_message": message,
        }
        if progress >= 8:
            current_job = self.db.get_job(job_id) or {}
            baseline_estimate = estimate_total_seconds(
                current_job.get("source_duration_seconds"),
                current_job.get("asr_quality") or self.settings.asr_quality,
                current_job.get("audio_profile") or self.settings.audio_profile,
                jobs=self.db.list_jobs(),
            )
            projected_total = elapsed / max(progress / 100.0, 0.01)
            current_estimate = current_job.get("estimated_total_seconds")
            if isinstance(current_estimate, (float, int)) and current_estimate > 0:
                # Never collapse ETA aggressively during ASR: diarization can still be the slowest phase.
                projected_total = max(projected_total, float(current_estimate) * 0.92)
            if isinstance(baseline_estimate, (float, int)) and baseline_estimate > 0:
                projected_total = max(projected_total, float(baseline_estimate) * 0.55)
            remaining_floor = estimate_stage_remaining_floor(
                stage,
                progress,
                baseline_estimate,
                elapsed,
            )
            fields["estimated_total_seconds"] = round(max(projected_total, elapsed + remaining_floor), 1)
        self.db.update_job(job_id, **fields)

    def ensure_not_cancelled(self, job_id: str) -> None:
        job = self.db.get_job(job_id)
        if job and job.get("cancel_requested"):
            raise JobCancelled("Processing was cancelled by user.")


def normalize_job(job: dict) -> dict:
    normalized = dict(job)
    normalized["warnings"] = load_json_field(normalized.pop("warnings_json", None), [])
    normalized["timings"] = load_json_field(normalized.pop("timings_json", None), {})
    return normalized


def load_json_field(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def normalize_choice(value: str | None, default: str, allowed: set[str]) -> str:
    normalized = (value or default).strip().lower()
    return normalized if normalized in allowed else default


def auto_audio_profile_for_quality(
    asr_quality: str,
    requested_profile: str | None = None,
    default_profile: str = "speech",
) -> str:
    if requested_profile:
        return normalize_choice(requested_profile, default_profile, {"plain", "speech", "conservative"})
    quality = normalize_choice(asr_quality, "balanced", {"fast", "balanced", "accurate"})
    if quality == "fast":
        return "conservative"
    return "speech"


def normalize_text_metadata(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def build_diarization_readiness_warnings(result, job: dict) -> list[str]:
    expected = job.get("expected_speaker_count")
    if result.diarization_status == "succeeded" and result.raw_speaker_count:
        return [
            (
                f"Acoustic diarization succeeded: found {result.raw_speaker_count} voice clusters"
                + (f", expected {expected}." if expected else ".")
            )
        ]
    if result.diarization_status in {"failed", "empty", "disabled"}:
        return [
            "Acoustic speaker separation is not reliable for this job; final speaker names can only be inferred from context."
        ]
    return []


def estimate_stage_remaining_floor(
    stage: str,
    progress: float,
    baseline_estimate: float | None,
    elapsed: float,
) -> float:
    baseline = baseline_estimate if isinstance(baseline_estimate, (float, int)) and baseline_estimate > 0 else None
    remaining_by_percent = ((100.0 - progress) / 100.0) * baseline if baseline else 0.0
    if stage == "asr":
        # ASR is only an early slice of the full pipeline; diarization is often the longest phase.
        return max(remaining_by_percent, 300.0)
    if stage == "diarization":
        # Pyannote does not provide fine-grained progress here; avoid fake "1 sec left" while it runs.
        return max((baseline or elapsed) * 0.20, 120.0)
    if stage in {"preprocess", "starting"}:
        return max((baseline or elapsed) * 0.70, 120.0)
    if stage == "postprocess":
        return max(30.0, remaining_by_percent)
    if stage == "export":
        return max(10.0, remaining_by_percent)
    return max(60.0, remaining_by_percent)


def remove_path_if_inside_data(value: object, data_dir: Path) -> None:
    if not value:
        return
    path = Path(value)
    try:
        resolved = path.resolve()
        data_root = data_dir.resolve()
        if resolved != data_root and data_root not in resolved.parents:
            return
        if resolved.is_dir():
            shutil.rmtree(resolved, ignore_errors=True)
        elif resolved.exists():
            resolved.unlink(missing_ok=True)
    except OSError:
        LOGGER.warning("Could not remove job artifact %s", value)


def write_raw_asr_artifacts(
    output_dir: Path,
    raw_text: str,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_text_path = output_dir / "raw_asr.txt"
    raw_text_path.write_text(raw_text.strip() + ("\n" if raw_text.strip() else ""), encoding="utf-8")
    return {"raw_txt": raw_text_path}


def build_readable_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    lower_message = message.lower()
    if "cublas64_12.dll" in lower_message or "cudnn" in lower_message:
        return (
            "Не удалось загрузить CUDA runtime для faster-whisper. "
            "Приложение попробовало CUDA float16, CUDA int8_float16 и CPU int8. "
            f"Техническая причина: {message}. "
            "Подробный traceback записан в backend/data/logs/backend.log."
        )
    return f"{message}\n\nПодробный traceback записан в backend/data/logs/backend.log."
