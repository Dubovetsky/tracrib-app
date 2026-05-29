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


def test_default_fast_estimate_reflects_asr_only_draft_mode():
    assert estimate_total_seconds(3600, "fast", "conservative", jobs=[]) == 339.0


def test_draft_runs_do_not_calibrate_full_diarization_modes():
    jobs = [
        {
            "status": "completed",
            "asr_quality": "balanced",
            "audio_profile": "speech",
            "source_duration_seconds": 3600.0,
            "timings_json": '{"total_job_seconds": 519.0}',
        }
    ]

    assert estimate_total_seconds(3600, "accurate", "speech", jobs=jobs) > 2000.0


def test_default_balanced_estimate_is_draft_plus_cleanup_not_full_diarization():
    assert estimate_total_seconds(3600, "balanced", "speech", jobs=[]) == 1527.0


def test_local_fallback_balanced_estimate_is_not_medium_provider_path():
    assert estimate_total_seconds(3600, "balanced_local", "conservative", jobs=[]) == 483.0


def test_legacy_balanced_full_diarization_run_does_not_poison_draft_eta():
    jobs = [
        {
            "status": "completed",
            "asr_quality": "balanced",
            "audio_profile": "speech",
            "source_duration_seconds": 5963.8,
            "timings_json": '{"total_job_seconds": 4039.3, "diarization_seconds": 3913.1}',
        }
    ]

    assert estimate_total_seconds(5963.8, "balanced", "speech", jobs=jobs) == 2519.8


def test_performance_summary_reports_one_hour_estimates():
    summary = performance_summary([])

    assert summary["hardware"]["cpu_count"] >= 1
    assert summary["calibrated_samples"] == 0
    assert summary["one_hour_estimates_seconds"]["accurate"]["speech"] is not None
