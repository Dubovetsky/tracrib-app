from __future__ import annotations

import os
import site
import sys
from pathlib import Path

from .diarization import DiarizationEngine, apply_diarization
from .exports import TranscriptSegment
from .postprocess import postprocess_transcript


_CUDA_DLL_DIRS: list[object] = []
_CUDA_DLL_DIRS_ADDED = False


def _add_windows_cuda_dll_dirs() -> None:
    global _CUDA_DLL_DIRS_ADDED
    if _CUDA_DLL_DIRS_ADDED or sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return

    candidates: list[Path] = []
    for site_dir in site.getsitepackages():
        root = Path(site_dir) / "nvidia"
        candidates.extend([root / "cublas" / "bin", root / "cudnn" / "bin"])

    for candidate in candidates:
        if candidate.exists():
            _CUDA_DLL_DIRS.append(os.add_dll_directory(str(candidate)))
    _CUDA_DLL_DIRS_ADDED = True


class FasterWhisperEngine:
    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        fallback_compute_type: str,
        diarization_engine: DiarizationEngine | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.fallback_compute_type = fallback_compute_type
        self.diarization_engine = diarization_engine
        self._model = None

    def _load_model(self):
        from faster_whisper import WhisperModel

        if self._model is not None:
            return self._model

        _add_windows_cuda_dll_dirs()
        try:
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
        except Exception:
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.fallback_compute_type,
            )
        return self._model

    def transcribe(self, audio_path: Path, language: str = "ru") -> tuple[str, list[TranscriptSegment]]:
        model = self._load_model()
        raw_segments, _ = model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
            beam_size=5,
        )
        segments: list[TranscriptSegment] = []
        for segment in raw_segments:
            text = segment.text.strip()
            if not text:
                continue
            segments.append({"start": float(segment.start), "end": float(segment.end), "text": text})
        if not segments:
            return "", []
        if self.diarization_engine is not None:
            try:
                turns = self.diarization_engine.diarize(audio_path)
                segments = apply_diarization(segments, turns)
            except Exception:
                pass
        return postprocess_transcript(segments, language=language)
