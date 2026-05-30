from pathlib import Path

from backend.app.diarization import load_audio_for_pyannote


def test_load_audio_for_pyannote_returns_preloaded_waveform(monkeypatch):
    class FakeTorchaudio:
        @staticmethod
        def load(path: str):
            return "waveform", 16000

    monkeypatch.setitem(__import__("sys").modules, "torchaudio", FakeTorchaudio)

    audio = load_audio_for_pyannote(Path("input.wav"))

    assert audio == {"waveform": "waveform", "sample_rate": 16000}
