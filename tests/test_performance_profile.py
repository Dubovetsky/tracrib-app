from backend.app.performance import estimate_total_seconds, performance_summary


def test_estimate_uses_completed_job_calibration():
    jobs = [
        {
            "status": "completed",
            "asr_quality": "accurate",
            "audio_profile": "speech",
            "source_duration_seconds": 1000.0,
            "timings_json": '{"total_job_seconds": 50.0}',
        },
        {
            "status": "completed",
            "asr_quality": "accurate",
            "audio_profile": "speech",
            "source_duration_seconds": 1000.0,
            "timings_json": '{"total_job_seconds": 700.0}',
        },
    ]

    assert estimate_total_seconds(200, "accurate", "speech", jobs=jobs) == 90.0


def test_single_long_fast_run_calibrates_immediately():
    jobs = [
        {
            "status": "completed",
            "asr_quality": "fast",
            "audio_profile": "speech",
            "source_duration_seconds": 5400.0,
            "timings_json": '{"total_job_seconds": 900.0}',
        }
    ]

    assert estimate_total_seconds(3600, "fast", "speech", jobs=jobs) == 615.1


def test_performance_summary_reports_one_hour_estimates():
    summary = performance_summary([])

    assert summary["hardware"]["cpu_count"] >= 1
    assert summary["calibrated_samples"] == 0
    assert summary["one_hour_estimates_seconds"]["accurate"]["speech"] is not None
