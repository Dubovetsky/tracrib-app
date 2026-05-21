from types import SimpleNamespace
from pathlib import Path

from backend.app.services import build_readable_error
from backend.app.hf_env import remove_dead_local_proxy
from backend.app.transcriber import FasterWhisperEngine, TranscriptionError


def test_faster_whisper_load_model_falls_back_to_cpu_int8(monkeypatch):
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

    text, segments = engine.transcribe(Path("input.wav"))

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


def test_faster_whisper_uses_quality_hints_and_word_timestamps(monkeypatch):
    captured_kwargs = {}

    class FakeWhisperModel:
        def __init__(self, model_name: str, device: str, compute_type: str) -> None:
            pass

        def transcribe(self, audio_path: str, **kwargs):
            captured_kwargs.update(kwargs)
            word = SimpleNamespace(start=0.0, end=0.4, word="EADR")
            segment = SimpleNamespace(start=0.0, end=0.4, text="EADR", words=[word])
            return [segment], None

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
        initial_prompt="EADR ADR Jira",
        hotwords="EADR ADR Jira",
    )

    _, segments = engine.transcribe(Path("input.wav"))

    assert captured_kwargs["word_timestamps"] is True
    assert captured_kwargs["condition_on_previous_text"] is False
    assert captured_kwargs["initial_prompt"] == "EADR ADR Jira"
    assert captured_kwargs["hotwords"] == "EADR ADR Jira"
    assert segments[0]["text"] == "EADR"


def test_participant_names_do_not_leak_into_asr_prompt_or_transcript(monkeypatch):
    captured_kwargs = {}

    class FakeWhisperModel:
        def __init__(self, model_name: str, device: str, compute_type: str) -> None:
            pass

        def transcribe(self, audio_path: str, **kwargs):
            captured_kwargs.update(kwargs)
            return [
                SimpleNamespace(start=0.0, end=1.0, text="Слава, Леонид, Карина. Слава, Леонид, Карина."),
                SimpleNamespace(start=1.0, end=2.0, text="Кто ведет заметки?"),
            ], None

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
        initial_prompt="Русская деловая встреча",
        hotwords="ADR EADR Jira",
    )

    result = engine.transcribe(
        Path("input.wav"),
        participant_names="Слава, Леонид, Карина",
        custom_vocabulary="SIEM, RPOINT, ADR, EADR",
    )

    assert "Слава" not in captured_kwargs["initial_prompt"]
    assert "Леонид" not in captured_kwargs["hotwords"]
    assert "SIEM" not in captured_kwargs["hotwords"]
    assert result.raw_text == "Кто ведет заметки?"
    assert "Слава, Леонид, Карина. Слава" not in result.text
    assert any("prompt-echo segment removed" in warning for warning in result.warnings)


def test_custom_vocabulary_echo_prefix_is_removed_without_dropping_real_text(monkeypatch):
    class FakeWhisperModel:
        def __init__(self, model_name: str, device: str, compute_type: str) -> None:
            pass

        def transcribe(self, audio_path: str, **kwargs):
            return [
                SimpleNamespace(
                    start=0.0,
                    end=3.0,
                    text=(
                        "SIEM, RPOINT, ADR, EADR. "
                        "Условная команда сканера. На них это шифрование влияет номинально."
                    ),
                )
            ], None

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
        hotwords="ADR EADR Jira",
    )

    result = engine.transcribe(Path("input.wav"), custom_vocabulary="SIEM, RPOINT, ADR, EADR")

    assert result.raw_text == "Условная команда сканера. На них это шифрование влияет номинально."
    assert result.text.startswith("Спикер 1:\nУсловная команда сканера.")
    assert any("prompt-echo prefix removed" in warning for warning in result.warnings)


def test_faster_whisper_reports_diarization_failure(monkeypatch):
    class FakeWhisperModel:
        def __init__(self, model_name: str, device: str, compute_type: str) -> None:
            pass

        def transcribe(self, audio_path: str, **kwargs):
            return [SimpleNamespace(start=0.0, end=1.0, text="РўРµСЃС‚")], None

    class BrokenDiarization:
        def diarize(self, audio_path: Path, expected_speakers: int | None = None):
            raise RuntimeError("pyannote unavailable")

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
        diarization_engine=BrokenDiarization(),
    )

    result = engine.transcribe(Path("input.wav"))

    assert result.diarization_status == "failed"
    assert result.speaker_count >= 1
    assert any("Diarization failed" in warning for warning in result.warnings)
    assert "asr_seconds" in result.timings
    assert "diarization_seconds" in result.timings


def test_faster_whisper_passes_expected_speaker_count_to_diarization(monkeypatch):
    captured_expected_speakers = None

    class FakeWhisperModel:
        def __init__(self, model_name: str, device: str, compute_type: str) -> None:
            pass

        def transcribe(self, audio_path: str, **kwargs):
            word = SimpleNamespace(start=0.0, end=0.5, word="РўРµСЃС‚")
            return [SimpleNamespace(start=0.0, end=1.0, text="РўРµСЃС‚", words=[word])], None

    class CapturingDiarization:
        def diarize(self, audio_path: Path, expected_speakers: int | None = None):
            nonlocal captured_expected_speakers
            captured_expected_speakers = expected_speakers
            return []

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
        diarization_engine=CapturingDiarization(),
    )

    engine.transcribe(Path("input.wav"), expected_speakers=3)

    assert captured_expected_speakers == 3


def test_accurate_asr_falls_back_to_default_model_when_large_model_unavailable(monkeypatch):
    loaded_models: list[str] = []

    class FakeWhisperModel:
        def __init__(self, model_name: str, device: str, compute_type: str) -> None:
            loaded_models.append(model_name)
            if model_name == "large-v3":
                raise RuntimeError("large model unavailable")

        def transcribe(self, audio_path: str, **kwargs):
            return [SimpleNamespace(start=0.0, end=1.0, text="fallback ok")], None

    monkeypatch.setitem(
        __import__("sys").modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeWhisperModel),
    )

    engine = FasterWhisperEngine(
        model_name="large-v3-turbo",
        accurate_model_name="large-v3",
        device="cuda",
        compute_type="float16",
        fallback_compute_type="int8_float16",
    )

    result = engine.transcribe(Path("input.wav"), asr_quality="accurate")

    assert "large-v3" in loaded_models
    assert "large-v3-turbo" in loaded_models
    assert result.raw_text == "fallback ok"
    assert any("Accurate ASR model unavailable" in warning for warning in result.warnings)


def test_remove_dead_local_proxy_keeps_real_proxy(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example:8080")

    remove_dead_local_proxy()

    assert "HTTPS_PROXY" not in __import__("os").environ
    assert __import__("os").environ["HTTP_PROXY"] == "http://proxy.example:8080"
