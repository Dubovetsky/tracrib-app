from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

from .services import JobService
from .settings import settings

app = FastAPI(title="Transcrib App", version="0.1.0")
service = JobService(settings)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    await service.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await service.stop()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    return service.list_jobs()


@app.post("/api/upload", status_code=201)
async def upload_audio(
    file: UploadFile = File(...),
    expected_speakers: int | None = Form(default=None),
    asr_quality: str | None = Form(default=None),
    audio_profile: str | None = Form(default=None),
    participant_names: str | None = Form(default=None),
    custom_vocabulary: str | None = Form(default=None),
) -> dict:
    if expected_speakers is not None and not 1 <= expected_speakers <= 20:
        raise HTTPException(status_code=422, detail="expected_speakers must be between 1 and 20")
    return await service.create_upload_job(
        file,
        expected_speakers=expected_speakers,
        asr_quality=asr_quality,
        audio_profile=audio_profile,
        participant_names=participant_names,
        custom_vocabulary=custom_vocabulary,
    )


@app.get("/api/diarization/readiness")
def diarization_readiness() -> dict:
    return service.diarization_readiness()


@app.get("/api/performance-profile")
def performance_profile() -> dict:
    return service.performance_profile()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: str) -> Response:
    if not service.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return Response(status_code=204)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    if not service.cancel_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    job = service.get_job(job_id)
    return job or {"id": job_id, "status": "failed"}


@app.get("/api/jobs/{job_id}/result", response_class=PlainTextResponse)
def get_result(job_id: str) -> str:
    job = get_completed_job(job_id)
    text_path = Path(job["text_path"])
    return text_path.read_text(encoding="utf-8")


@app.get("/api/jobs/{job_id}/download/txt")
def download_txt(job_id: str) -> FileResponse:
    return download_result(job_id, "text_path", "transcript.txt", "text/plain")


@app.get("/api/jobs/{job_id}/download/raw-txt")
def download_raw_txt(job_id: str) -> FileResponse:
    return download_result(
        job_id,
        "raw_text_path",
        "raw_asr.txt",
        "text/plain",
        fallback_fields=("text_path",),
    )


def get_completed_job(job_id: str) -> dict:
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job is {job['status']}")
    return job


def download_result(
    job_id: str,
    field: str,
    filename: str,
    media_type: str,
    fallback_fields: tuple[str, ...] = (),
) -> FileResponse:
    job = get_completed_job(job_id)
    path = first_existing_job_path(job, (field, *fallback_fields))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    return FileResponse(path, filename=filename, media_type=media_type)


def first_existing_job_path(job: dict, fields: tuple[str, ...]) -> Path:
    for field in fields:
        value = job.get(field)
        if not value:
            continue
        path = Path(value)
        if path.exists():
            return path
    raise HTTPException(status_code=404, detail="Result file not found")
