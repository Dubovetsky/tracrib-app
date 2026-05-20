from types import SimpleNamespace

from backend.app.services import build_readable_error
from backend.app.transcriber import FasterWhisperEngine, TranscriptionError


def test_faster_whisper_load_model_falls_back_to_cpu_int8(monkeypatch, tmp_path):
    attempts: list[tuple[str, str]] = []

    class FakeWhisperModel:
        def __init__(self, model_name: str, device: str, compute_type: str) -> None:
            attempts.append((device, compute_type))
            if device == "cuda":
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")

        def transcribe(self, audio_path: str, **kwargs):
            return [SimpleNamespace(start=0.0, end=1.0, text="Тест")], None

    monkeypatch.setitem(
        __import__("sys").modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeWhisperModel),
    )

    engine = FasterWhisperEngine(
        model_name="test-model",
        device="cuda",
        compute_type="float16",
        fallback_compute_type="int8_float16",
    )

    text, segments = engine.transcribe(tmp_path / "input.wav")

    assert attempts == [("cuda", "float16"), ("cuda", "int8_float16"), ("cpu", "int8")]
    assert engine.device == "cpu"
    assert engine.compute_type == "int8"
    assert segments[0]["text"] == "Тест"
    assert "Тест" in text


def test_faster_whisper_load_model_reports_all_failed_attempts(monkeypatch):
    class FakeWhisperModel:
        def __init__(self, model_name: str, device: str, compute_type: str) -> None:
            raise RuntimeError(f"{device}/{compute_type} failed")

    monkeypatch.setitem(
        __import__("sys").modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeWhisperModel),
    )

    engine = FasterWhisperEngine(
        model_name="test-model",
        device="cuda",
        compute_type="float16",
        fallback_compute_type="int8_float16",
    )

    try:
        engine._load_model()
    except TranscriptionError as exc:
        message = str(exc)
    else:
        raise AssertionError("TranscriptionError was not raised")

    assert "CUDA float16" in message
    assert "cuda/float16 failed" in message
    assert "cuda/int8_float16 failed" in message
    assert "cpu/int8 failed" in message


def test_build_readable_error_mentions_cuda_fallback_and_log_path():
    error = build_readable_error(RuntimeError("Library cublas64_12.dll is not found or cannot be loaded"))

    assert "CUDA float16" in error
    assert "CUDA int8_float16" in error
    assert "CPU int8" in error
    assert "backend/data/logs/backend.log" in error
