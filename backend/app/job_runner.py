from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .services import JobService
from .settings import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one transcription job in an isolated worker process.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()

    os.environ["TRANSCRIB_APP_DATA_DIR"] = args.data_dir
    os.environ["JOB_SUBPROCESS_ENABLED"] = "0"
    service = JobService(Settings(data_dir=Path(args.data_dir), job_subprocess_enabled=False))
    service.process_job(args.job_id)
    job = service.db.get_job(args.job_id)
    if job and job.get("status") in {"completed", "failed"}:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
