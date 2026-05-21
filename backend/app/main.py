from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
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
) -> dict:
    if expected_speakers is not None and not 1 <= expected_speakers <= 12:
        raise HTTPException(status_code=422, detail="expected_speakers must be between 1 and 12")
    return await service.create_upload_job(file, expected_speakers=expected_speakers)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs/{job_id}/result", response_class=PlainTextResponse)
def get_result(job_id: str) -> str:
    job = get_completed_job(job_id)
    text_path = Path(job["text_path"])
    return text_path.read_text(encoding="utf-8")


@app.get("/api/jobs/{job_id}/download/txt")
def download_txt(job_id: str) -> FileResponse:
    return download_result(job_id, "text_path", "transcript.txt", "text/plain")


@app.get("/api/jobs/{job_id}/download/srt")
def download_srt(job_id: str) -> FileResponse:
    return download_result(job_id, "srt_path", "transcript.srt", "application/x-subrip")


@app.get("/api/jobs/{job_id}/download/vtt")
def download_vtt(job_id: str) -> FileResponse:
    return download_result(job_id, "vtt_path", "transcript.vtt", "text/vtt")


@app.get("/api/jobs/{job_id}/download/diagnostics")
def download_diagnostics(job_id: str) -> FileResponse:
    return download_result(job_id, "diagnostics_json_path", "diagnostics.json", "application/json")


@app.get("/api/jobs/{job_id}/download/diarization-turns")
def download_diarization_turns(job_id: str) -> FileResponse:
    return download_result(job_id, "diarization_turns_path", "diarization_turns.json", "application/json")


@app.get("/api/jobs/{job_id}/download/segments")
def download_segments(job_id: str) -> FileResponse:
    return download_result(job_id, "segments_json_path", "segments.json", "application/json")


def get_completed_job(job_id: str) -> dict:
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job is {job['status']}")
    return job


def download_result(job_id: str, field: str, filename: str, media_type: str) -> FileResponse:
    job = get_completed_job(job_id)
    path = Path(job[field])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    return FileResponse(path, filename=filename, media_type=media_type)
