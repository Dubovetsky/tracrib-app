from __future__ import annotations

from pathlib import Path

from .exports import TranscriptSegment


class FasterWhisperEngine:
    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        fallback_compute_type: str,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.fallback_compute_type = fallback_compute_type
        self._model = None

    def _load_model(self):
        from faster_whisper import WhisperModel

        if self._model is not None:
            return self._model

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
        text_parts: list[str] = []
        for segment in raw_segments:
            text = segment.text.strip()
            if not text:
                continue
            segments.append({"start": float(segment.start), "end": float(segment.end), "text": text})
            text_parts.append(text)
        return " ".join(text_parts), segments
