from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    original_filename TEXT NOT NULL,
                    stored_audio_path TEXT NOT NULL,
                    preprocessed_audio_path TEXT,
                    text_path TEXT,
                    srt_path TEXT,
                    vtt_path TEXT,
                    status TEXT NOT NULL,
                    language TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                )
                """
            )
            conn.commit()

    def create_job(self, job: dict[str, Any]) -> None:
        now = utc_now()
        payload = {
            "id": job["id"],
            "original_filename": job["original_filename"],
            "stored_audio_path": job["stored_audio_path"],
            "status": job.get("status", "queued"),
            "language": job.get("language", "ru"),
            "created_at": now,
            "updated_at": now,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, original_filename, stored_audio_path, status,
                    language, created_at, updated_at
                )
                VALUES (
                    :id, :original_filename, :stored_audio_path, :status,
                    :language, :created_at, :updated_at
                )
                """,
                payload,
            )
            conn.commit()

    def update_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = :{key}" for key in fields)
        fields["id"] = job_id
        with self.connect() as conn:
            conn.execute(f"UPDATE jobs SET {assignments} WHERE id = :id", fields)
            conn.commit()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
