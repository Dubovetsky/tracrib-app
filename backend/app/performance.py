from __future__ import annotations

import json
import os
import platform
import statistics
from dataclasses import dataclass
from typing import Any


# Baseline total real-time factors for CUDA-class local processing with diarization.
# Example: 0.17 means roughly 10 minutes for 1 hour of audio.
QUALITY_BASE_RTF = {
    "fast": 0.16,
    "balanced": 0.29,
    "accurate": 0.58,
}

PROFILE_EXTRA_RTF = {
    "plain": 0.0,
    "conservative": 0.01,
    "speech": 0.02,
}

FIXED_OVERHEAD_SECONDS = 15.0
MIN_CALIBRATION_DURATION_SECONDS = 300.0
MIN_RTF = 0.05
MAX_RTF = 3.0


@dataclass(frozen=True)
class HardwareProfile:
    cpu_count: int
    system: str
    machine: str
    cuda_available: bool
    gpu_name: str | None
    estimate_source: str

    @property
    def speed_multiplier(self) -> float:
        if self.cuda_available:
            return 1.0
        if self.cpu_count >= 16:
            return 3.2
        if self.cpu_count >= 8:
            return 4.5
        return 6.0

    def as_dict(self) -> dict[str, object]:
        return {
            "cpu_count": self.cpu_count,
            "system": self.system,
            "machine": self.machine,
            "cuda_available": self.cuda_available,
            "gpu_name": self.gpu_name,
            "estimate_source": self.estimate_source,
        }


def detect_hardware_profile() -> HardwareProfile:
    cuda_available = False
    gpu_name: str | None = None
    estimate_source = "hardware-default"
    try:
        import ctranslate2  # type: ignore

        if ctranslate2.get_cuda_device_count() > 0:
            cuda_available = True
            estimate_source = "ctranslate2-cuda"
    except Exception:
        pass

    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            cuda_available = True
            gpu_name = torch.cuda.get_device_name(0)
            estimate_source = "torch-cuda"
    except Exception:
        pass

    configured_device = os.getenv("WHISPER_DEVICE", "").strip().lower()
    if not cuda_available and configured_device == "cuda":
        cuda_available = True
        estimate_source = "configured-cuda"

    if not cuda_available:
        estimate_source = "cpu-hardware-default"

    return HardwareProfile(
        cpu_count=os.cpu_count() or 1,
        system=platform.system(),
        machine=platform.machine(),
        cuda_available=cuda_available,
        gpu_name=gpu_name,
        estimate_source=estimate_source,
    )


def estimate_total_seconds(
    duration_seconds: object,
    quality: str,
    profile: str = "speech",
    jobs: list[dict[str, Any]] | None = None,
    hardware: HardwareProfile | None = None,
) -> float | None:
    if not isinstance(duration_seconds, (float, int)) or duration_seconds <= 0:
        return None

    calibrated_rtf = calibrated_realtime_factor(jobs or [], quality, profile)
    if calibrated_rtf is not None:
        realtime_factor = calibrated_rtf
    else:
        hardware = hardware or detect_hardware_profile()
        realtime_factor = default_realtime_factor(quality, profile) * hardware.speed_multiplier

    return round(float(duration_seconds) * realtime_factor + FIXED_OVERHEAD_SECONDS, 1)


def default_realtime_factor(quality: str, profile: str = "speech") -> float:
    return (
        QUALITY_BASE_RTF.get(quality, QUALITY_BASE_RTF["balanced"])
        + PROFILE_EXTRA_RTF.get(profile, PROFILE_EXTRA_RTF["speech"])
    )


def calibrated_realtime_factor(
    jobs: list[dict[str, Any]],
    quality: str,
    profile: str,
) -> float | None:
    exact_samples: list[float] = []
    scale_samples: list[float] = []
    for job in jobs:
        if job.get("status") != "completed":
            continue
        job_quality = job.get("asr_quality") or "balanced"
        job_profile = job.get("audio_profile") or "speech"
        duration = job.get("source_duration_seconds")
        timings = parse_json_object(job.get("timings_json"))
        total = timings.get("total_job_seconds") or job.get("estimated_total_seconds")
        if not isinstance(duration, (float, int)) or not isinstance(total, (float, int)):
            continue
        if duration < MIN_CALIBRATION_DURATION_SECONDS or total <= 0:
            continue
        sample_rtf = clamp_rtf(float(total) / float(duration))
        if job_quality == quality and job_profile == profile:
            exact_samples.append(sample_rtf)
        baseline = default_realtime_factor(str(job_quality), str(job_profile))
        if baseline > 0:
            scale_samples.append(sample_rtf / baseline)

    if exact_samples:
        return round(statistics.median(exact_samples[-10:]), 4)
    if scale_samples:
        machine_scale = statistics.median(scale_samples[-10:])
        return round(clamp_rtf(default_realtime_factor(quality, profile) * machine_scale), 4)
    return None


def performance_summary(jobs: list[dict[str, Any]] | None = None) -> dict[str, object]:
    jobs = jobs or []
    hardware = detect_hardware_profile()
    sample_count = count_calibration_samples(jobs)
    estimates: dict[str, dict[str, float | None]] = {}
    for quality in ("accurate", "balanced", "fast"):
        estimates[quality] = {}
        for profile in ("speech", "conservative", "plain"):
            estimates[quality][profile] = estimate_total_seconds(
                3600,
                quality,
                profile,
                jobs=jobs,
                hardware=hardware,
            )
    return {
        "hardware": hardware.as_dict(),
        "calibrated_samples": sample_count,
        "one_hour_estimates_seconds": estimates,
    }


def count_calibration_samples(jobs: list[dict[str, Any]]) -> int:
    count = 0
    for job in jobs:
        duration = job.get("source_duration_seconds")
        timings = parse_json_object(job.get("timings_json"))
        total = timings.get("total_job_seconds") or job.get("estimated_total_seconds")
        if (
            job.get("status") == "completed"
            and isinstance(duration, (float, int))
            and duration >= MIN_CALIBRATION_DURATION_SECONDS
            and isinstance(total, (float, int))
        ):
            count += 1
    return count


def clamp_rtf(value: float) -> float:
    return max(MIN_RTF, min(MAX_RTF, value))


def parse_json_object(value: object) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
