from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from dataclasses import dataclass
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
from .text_polish import TextPolishConfig, build_provider_chain, polish_transcript
from .transcriber import FasterWhisperEngine


LOGGER = logging.getLogger("transcrib_app.backend")


class JobCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class PipelinePlan:
    selected_mode: str
    actual_pipeline: str
    diarization_mode: str
    audio_profile: str
    run_full_diarization: bool
    text_polish_enabled: bool
    text_polish_provider: str
    text_polish_timeout_seconds: float | None
    time_budget_seconds: float | None


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


def attach_job_log_handler(log_path: Path) -> RotatingFileHandler:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=5_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    return handler


def detach_job_log_handler(handler: logging.Handler) -> None:
    LOGGER.removeHandler(handler)
    handler.close()


def terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


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
        self.active_processes: dict[str, subprocess.Popen] = {}

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
        for process in list(self.active_processes.values()):
            terminate_process(process)
        self.active_processes.clear()

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
        job_log_path = self.job_log_path(job_id)
        stored_path.parent.mkdir(parents=True, exist_ok=True)
        with stored_path.open("wb") as target:
            shutil.copyfileobj(upload.file, target)
        selected_quality = normalize_choice(asr_quality, self.settings.asr_quality, {"fast", "balanced", "accurate"})
        pipeline_plan = select_pipeline_plan(
            selected_quality,
            requested_audio_profile=audio_profile,
            default_audio_profile=self.settings.audio_profile,
        )
        selected_profile = pipeline_plan.audio_profile
        source_duration_seconds = probe_audio(stored_path).get("duration_seconds")
        text_polish_config = text_polish_config_for_pipeline(pipeline_plan, self.settings)
        text_analysis_status = text_analysis_status_for_pipeline(pipeline_plan, text_polish_config)
        estimate_quality = estimate_quality_for_pipeline(selected_quality, text_analysis_status)
        estimated_total_seconds = estimate_total_seconds(
            source_duration_seconds,
            estimate_quality,
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
                "diagnostics_json": json.dumps(
                    build_pipeline_diagnostics(
                        pipeline_plan,
                        speaker_separation_status="queued",
                        elapsed_time=None,
                        text_analysis_status=text_analysis_status,
                        text_analysis_provider=text_polish_config.provider,
                    ),
                    ensure_ascii=False,
                ),
                "job_log_path": str(job_log_path),
            }
        )
        await self.enqueue(job_id)
        return self.get_job(job_id)

    async def enqueue(self, job_id: str) -> None:
        if self.queue is None:
            self.queue = asyncio.Queue()
        await self.queue.put(job_id)
        self.ensure_worker_running()

    def ensure_worker_running(self) -> None:
        if self.queue is not None and (self.worker_task is None or self.worker_task.done()):
            self.worker_task = asyncio.create_task(self._worker())

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
            "job_log_path",
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
        pipeline_plan = select_pipeline_plan(
            job.get("asr_quality") or self.settings.asr_quality,
            requested_audio_profile=job.get("audio_profile"),
            default_audio_profile=self.settings.audio_profile,
        )
        self.db.update_job(
            job_id,
            status="failed",
            cancel_requested=1,
            processing_stage="cancelled",
            progress_message="Обработка прервана",
            error="Processing was cancelled by user.",
            diagnostics_json=json.dumps(
                build_pipeline_diagnostics(
                    pipeline_plan,
                    speaker_separation_status="cancelled",
                    elapsed_time=None,
                    fallback_used=True,
                    fallback_reason="cancelled by user",
                ),
                ensure_ascii=False,
            ),
            finished_at=utc_now(),
        )
        process = self.active_processes.get(job_id)
        if process and process.poll() is None:
            terminate_process(process)
            LOGGER.info("Job %s subprocess terminated on cancellation", job_id)
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
                try:
                    if self.should_run_job_in_subprocess():
                        await asyncio.to_thread(self.process_job_subprocess, job_id)
                    else:
                        await asyncio.to_thread(self.process_job, job_id)
                except Exception as exc:
                    LOGGER.exception("Worker failed while processing job %s", job_id)
                    latest = self.db.get_job(job_id)
                    if latest and latest.get("status") in {"queued", "processing"}:
                        self.db.update_job(
                            job_id,
                            status="failed",
                            processing_stage="failed",
                            progress_message="Обработка завершилась ошибкой",
                            error=build_readable_error(exc),
                            finished_at=utc_now(),
                        )
            finally:
                self.queue.task_done()

    def should_run_job_in_subprocess(self) -> bool:
        return self.settings.job_subprocess_enabled and isinstance(self.transcriber, FasterWhisperEngine)

    def job_log_path(self, job_id: str) -> Path:
        return self.settings.result_dir / job_id / "job.log"

    def process_job_subprocess(self, job_id: str) -> None:
        job = self.db.get_job(job_id)
        if not job:
            return
        if job.get("cancel_requested") or job.get("status") not in {"queued", "processing"}:
            return
        log_path = Path(job.get("job_log_path") or self.job_log_path(job_id))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.db.update_job(job_id, job_log_path=str(log_path), processing_stage="starting")
        command = [
            sys.executable,
            "-m",
            "backend.app.job_runner",
            "--data-dir",
            str(self.settings.data_dir),
            "--job-id",
            job_id,
        ]
        LOGGER.info("Job %s subprocess starting", job_id)
        try:
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"{utc_now()} INFO Parent starting subprocess: {' '.join(command)}\n")
                log_file.flush()
                process = subprocess.Popen(
                    command,
                    cwd=str(Path.cwd()),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                self.active_processes[job_id] = process
                return_code = process.wait()
        finally:
            self.active_processes.pop(job_id, None)
        latest = self.db.get_job(job_id)
        if latest and latest.get("cancel_requested"):
            return
        if return_code != 0 and latest and latest.get("status") in {"queued", "processing"}:
            self.db.update_job(
                job_id,
                status="failed",
                processing_stage="failed",
                progress_message="Обработка завершилась ошибкой",
                error=f"Worker process exited with code {return_code}. See job.log.",
                finished_at=utc_now(),
            )

    def process_job(self, job_id: str) -> None:
        job = self.db.get_job(job_id)
        if not job:
            return
        if job.get("cancel_requested") or job.get("status") not in {"queued", "processing"}:
            return

        job_log_path = Path(job.get("job_log_path") or self.job_log_path(job_id))
        job_handler = attach_job_log_handler(job_log_path)
        selected_quality = job.get("asr_quality") or self.settings.asr_quality
        pipeline_plan = select_pipeline_plan(
            selected_quality,
            requested_audio_profile=job.get("audio_profile"),
            default_audio_profile=self.settings.audio_profile,
        )
        total_started_at = time.perf_counter()
        try:
            self.db.update_job(
                job_id,
                status="processing",
                processing_stage="starting",
                progress_percent=1.0,
                progress_message="Запускаем обработку",
                started_at=utc_now(),
                error=None,
                job_log_path=str(job_log_path),
                diagnostics_json=json.dumps(
                    build_pipeline_diagnostics(
                        pipeline_plan,
                        speaker_separation_status="starting",
                        elapsed_time=0.0,
                    ),
                    ensure_ascii=False,
                ),
            )
            LOGGER.info("Job %s processing started", job_id)
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
                timeout_seconds=self.settings.audio_preprocess_timeout_seconds,
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
            raw_paths: dict[str, Path] | None = None

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

            def raw_asr_ready(raw_text: str, raw_segments: list[dict]) -> None:
                nonlocal raw_paths
                raw_paths = write_raw_asr_artifacts(
                    self.settings.result_dir / job_id,
                    raw_text,
                )
                self.db.update_job(
                    job_id,
                    raw_text_path=str(raw_paths["raw_txt"]),
                    progress_message="RAW ASR готов; продолжаем обработку",
                )
                LOGGER.info("Job %s raw ASR artifact is ready", job_id)

            result = self.transcriber.transcribe(
                wav_path,
                language=self.settings.language,
                expected_speakers=job.get("expected_speaker_count"),
                asr_quality=selected_quality,
                participant_names=job.get("participant_names") or "",
                custom_vocabulary=job.get("custom_vocabulary") or "",
                source_duration_seconds=job.get("source_duration_seconds"),
                progress_callback=transcriber_progress,
                raw_asr_callback=raw_asr_ready,
                run_diarization=pipeline_plan.run_full_diarization,
            )
            self.ensure_not_cancelled(job_id)
            timings.update(result.timings)
            warnings.extend(result.warnings)
            warnings.extend(build_diarization_readiness_warnings(result, job))
            if raw_paths is None:
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
            text_polish_config = text_polish_config_for_pipeline(pipeline_plan, self.settings)
            text_polish_provider = text_polish_config.provider
            text_analysis_status = text_analysis_status_for_pipeline(
                pipeline_plan,
                text_polish_config,
            )
            if pipeline_plan.selected_mode == "balanced":
                warnings.append(
                    (
                        "Balanced text-analysis pipeline used: ASR + bounded text cleanup "
                        "and speaker-structure heuristics; full acoustic diarization was not run."
                    )
                )
                if text_analysis_status == "local_fallback":
                    warnings.append(
                        (
                            "Balanced text analysis fell back to local rules because no configured "
                            "cloud text-polish provider API key is available. Quality will be closer "
                            "to Fast than to Maximum until a provider is configured."
                        )
                    )

            text, segments = polish_transcript(
                result.text,
                result.segments,
                text_polish_config,
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
            diagnostics = build_pipeline_diagnostics(
                pipeline_plan,
                speaker_separation_status=speaker_separation_status(pipeline_plan, result.diarization_status),
                elapsed_time=timings["total_job_seconds"],
                fallback_used=balanced_fallback_used(pipeline_plan, result.diarization_status),
                fallback_reason=balanced_fallback_reason(pipeline_plan, result.diarization_status),
                text_analysis_status=text_analysis_status,
                text_analysis_provider=text_polish_provider,
            )
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
                diagnostics_json=json.dumps(diagnostics, ensure_ascii=False),
                diarization_turns_path=None,
                segments_json_path=None,
                diagnostics_json_path=None,
                finished_at=utc_now(),
            )
            LOGGER.info("Job %s completed", job_id)
        except JobCancelled:
            LOGGER.info("Job %s cancelled", job_id)
            self.db.update_job(
                job_id,
                status="failed",
                cancel_requested=1,
                processing_stage="cancelled",
                progress_message="Обработка прервана",
                error="Processing was cancelled by user.",
                diagnostics_json=json.dumps(
                    build_pipeline_diagnostics(
                        pipeline_plan,
                        speaker_separation_status="cancelled",
                        elapsed_time=round(time.perf_counter() - total_started_at, 3),
                        fallback_used=True,
                        fallback_reason="cancelled by user",
                    ),
                    ensure_ascii=False,
                ),
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
                diagnostics_json=json.dumps(
                    build_pipeline_diagnostics(
                        pipeline_plan,
                        speaker_separation_status="failed",
                        elapsed_time=round(time.perf_counter() - total_started_at, 3),
                        fallback_used=True,
                        fallback_reason=str(exc).strip() or exc.__class__.__name__,
                    ),
                    ensure_ascii=False,
                ),
                finished_at=utc_now(),
            )
        finally:
            detach_job_log_handler(job_handler)

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
            quality = current_job.get("asr_quality") or self.settings.asr_quality
            diagnostics = load_json_field(current_job.get("diagnostics_json"), {})
            estimate_quality = estimate_quality_for_pipeline(
                quality,
                str(diagnostics.get("text_analysis_status") or ""),
            )
            baseline_estimate = estimate_total_seconds(
                current_job.get("source_duration_seconds"),
                estimate_quality,
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
                quality=quality,
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
    normalized["diagnostics"] = load_json_field(normalized.pop("diagnostics_json", None), {})
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


def select_pipeline_plan(
    asr_quality: str,
    requested_audio_profile: str | None = None,
    default_audio_profile: str = "speech",
) -> PipelinePlan:
    selected_mode = normalize_choice(asr_quality, "balanced", {"fast", "balanced", "accurate"})
    if selected_mode == "fast":
        return PipelinePlan(
            selected_mode="fast",
            actual_pipeline="fast_asr_only",
            diarization_mode="none",
            audio_profile=auto_audio_profile_for_quality(selected_mode, requested_audio_profile, default_audio_profile),
            run_full_diarization=False,
            text_polish_enabled=False,
            text_polish_provider="off",
            text_polish_timeout_seconds=None,
            time_budget_seconds=None,
        )
    if selected_mode == "accurate":
        return PipelinePlan(
            selected_mode="accurate",
            actual_pipeline="maximum_full_diarization",
            diarization_mode="full",
            audio_profile=auto_audio_profile_for_quality(selected_mode, requested_audio_profile, default_audio_profile),
            run_full_diarization=True,
            text_polish_enabled=True,
            text_polish_provider="configured",
            text_polish_timeout_seconds=None,
            time_budget_seconds=None,
        )
    return PipelinePlan(
        selected_mode="balanced",
        actual_pipeline="balanced_text_analysis",
        diarization_mode="lightweight",
        audio_profile=auto_audio_profile_for_quality(selected_mode, requested_audio_profile, default_audio_profile),
        run_full_diarization=False,
        text_polish_enabled=True,
        text_polish_provider="auto",
        text_polish_timeout_seconds=180.0,
        time_budget_seconds=1800.0,
    )


def build_pipeline_diagnostics(
    plan: PipelinePlan,
    speaker_separation_status: str,
    elapsed_time: float | None,
    fallback_used: bool = False,
    fallback_reason: str = "",
    text_analysis_status: str | None = None,
    text_analysis_provider: str | None = None,
) -> dict[str, object]:
    effective_time_budget = plan.time_budget_seconds
    if text_analysis_status == "local_fallback":
        effective_time_budget = None
    return {
        "selected_mode": plan.selected_mode,
        "actual_pipeline": plan.actual_pipeline,
        "diarization_mode": plan.diarization_mode,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "speaker_separation_status": speaker_separation_status,
        "time_budget": effective_time_budget,
        "elapsed_time": elapsed_time,
        "text_analysis_status": text_analysis_status or default_text_analysis_status(plan),
        "text_analysis_provider": text_analysis_provider or plan.text_polish_provider,
    }


def speaker_separation_status(plan: PipelinePlan, diarization_status: str) -> str:
    if plan.diarization_mode == "none":
        return "not_requested"
    if plan.diarization_mode == "lightweight":
        return "lightweight_completed" if diarization_status == "lightweight" else "lightweight_text_heuristics"
    return f"full_{diarization_status}"


def balanced_fallback_used(plan: PipelinePlan, diarization_status: str) -> bool:
    return plan.diarization_mode == "lightweight" and diarization_status in {"failed", "empty", "disabled"}


def balanced_fallback_reason(plan: PipelinePlan, diarization_status: str) -> str:
    if not balanced_fallback_used(plan, diarization_status):
        return ""
    return f"lightweight speaker separation fell back from {diarization_status} to text-only labels"


def auto_audio_profile_for_quality(
    asr_quality: str,
    requested_profile: str | None = None,
    default_profile: str = "speech",
) -> str:
    if requested_profile:
        return normalize_choice(requested_profile, default_profile, {"plain", "speech", "conservative"})
    quality = normalize_choice(asr_quality, "balanced", {"fast", "balanced", "accurate"})
    if quality in {"fast", "balanced"}:
        return "conservative"
    return "speech"


def text_polish_provider_for_quality(asr_quality: str, configured_provider: str) -> str:
    quality = normalize_choice(asr_quality, "balanced", {"fast", "balanced", "accurate"})
    if quality == "fast":
        return "off"
    return configured_provider


def text_polish_provider_for_pipeline(plan: PipelinePlan, configured_provider: str) -> str:
    if not plan.text_polish_enabled:
        return "off"
    configured = (configured_provider or "auto").strip().lower()
    if plan.selected_mode == "balanced":
        # Balanced is the bounded text-analysis mode. If the app-level setting was
        # left on local/off, force the old useful behavior: try provider chain,
        # then fall back loudly to local rules if no provider is configured.
        if configured in {"", "off", "none", "disabled", "local"}:
            return "auto"
    return configured_provider


def text_polish_config_for_pipeline(plan: PipelinePlan, settings: Settings) -> TextPolishConfig:
    return TextPolishConfig(
        provider=text_polish_provider_for_pipeline(plan, settings.text_polish_provider),
        providers=settings.text_polish_providers,
        model=settings.text_polish_model,
        timeout_seconds=text_polish_timeout_for_pipeline(plan, settings.text_polish_timeout_seconds),
        openai_api_key=settings.openai_api_key,
    )


def text_polish_timeout_for_pipeline(plan: PipelinePlan, configured_timeout: float) -> float:
    if plan.text_polish_timeout_seconds is None:
        return configured_timeout
    return max(float(configured_timeout), plan.text_polish_timeout_seconds)


def text_analysis_status_for_pipeline(plan: PipelinePlan, config: TextPolishConfig) -> str:
    if not plan.text_polish_enabled:
        return "skipped"
    provider = config.provider.lower().strip()
    if plan.selected_mode == "balanced" and provider == "auto" and not build_provider_chain(config):
        return "local_fallback"
    if provider == "local":
        return "local"
    if provider in {"off", "none", "disabled"}:
        return "skipped"
    return "provider_chain"


def default_text_analysis_status(plan: PipelinePlan) -> str:
    if not plan.text_polish_enabled:
        return "skipped"
    if plan.selected_mode == "balanced":
        return "pending"
    return "enabled"


def estimate_quality_for_pipeline(asr_quality: str, text_analysis_status: str) -> str:
    quality = normalize_choice(asr_quality, "balanced", {"fast", "balanced", "accurate"})
    if quality == "balanced" and text_analysis_status == "local_fallback":
        return "balanced_local"
    return quality


def should_run_diarization_for_quality(asr_quality: str) -> bool:
    quality = normalize_choice(asr_quality, "balanced", {"fast", "balanced", "accurate"})
    return quality == "accurate"


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
    if result.diarization_status == "lightweight":
        return [
            (
                f"Lightweight speaker separation assigned {result.raw_speaker_count or result.speaker_count} speaker labels"
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
    quality: str | None = None,
) -> float:
    baseline = baseline_estimate if isinstance(baseline_estimate, (float, int)) and baseline_estimate > 0 else None
    remaining_by_percent = ((100.0 - progress) / 100.0) * baseline if baseline else 0.0
    if stage == "asr":
        if quality == "fast":
            return max(remaining_by_percent, 30.0)
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
            "Подробный traceback записан в job.log для этой записи."
        )
    return f"{message}\n\nПодробный traceback записан в job.log для этой записи."
