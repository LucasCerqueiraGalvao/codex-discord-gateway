from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class AudioTranscription:
    text: str
    duration_seconds: float | None
    detected_language: str | None


class AudioTranscriptionError(RuntimeError):
    pass


class AudioTooLongError(AudioTranscriptionError):
    def __init__(self, duration_seconds: float, max_duration_seconds: int) -> None:
        self.duration_seconds = duration_seconds
        self.max_duration_seconds = max_duration_seconds
        super().__init__(
            f"audio com {duration_seconds:.1f}s excede limite de {max_duration_seconds}s"
        )


class LocalAudioTranscriber:
    def __init__(
        self,
        model_name: str = "small",
        language: str | None = "pt",
        device: str = "cpu",
        compute_type: str = "int8",
        logger: logging.Logger | None = None,
    ) -> None:
        self._model_name = model_name.strip() or "small"
        self._language = (language or "").strip() or None
        self._device = device.strip() or "cpu"
        self._compute_type = compute_type.strip() or "int8"
        self._logger = logger or logging.getLogger(__name__)
        self._model = None
        self._model_lock = Lock()

    def _load_model(self):
        if self._model is not None:
            return self._model

        with self._model_lock:
            if self._model is not None:
                return self._model
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise AudioTranscriptionError(
                    "Dependencia de STT ausente/incompleta "
                    f"({exc}). Rode: pip install faster-whisper requests"
                ) from exc

            self._logger.info(
                "Loading faster-whisper model '%s' (device=%s, compute_type=%s)",
                self._model_name,
                self._device,
                self._compute_type,
            )
            self._model = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )
            return self._model

    def _read_duration_seconds(self, audio_path: Path) -> float | None:
        try:
            import av
        except ImportError:
            return None

        try:
            with av.open(str(audio_path)) as container:
                if container.duration:
                    duration = float(container.duration) / 1_000_000.0
                    if duration > 0:
                        return duration

                for stream in container.streams.audio:
                    if stream.duration is None or stream.time_base is None:
                        continue
                    duration = float(stream.duration * stream.time_base)
                    if duration > 0:
                        return duration
        except Exception as exc:
            self._logger.warning("Could not read audio duration for %s: %s", audio_path, exc)
        return None

    def transcribe(
        self,
        audio_path: Path,
        *,
        max_duration_seconds: int,
    ) -> AudioTranscription:
        if not audio_path.exists():
            raise AudioTranscriptionError(f"arquivo nao encontrado: {audio_path}")

        duration_seconds = self._read_duration_seconds(audio_path)
        if (
            isinstance(duration_seconds, (int, float))
            and max_duration_seconds > 0
            and duration_seconds > max_duration_seconds
        ):
            raise AudioTooLongError(float(duration_seconds), max_duration_seconds)

        model = self._load_model()

        try:
            segments, info = model.transcribe(
                str(audio_path),
                language=self._language,
                task="transcribe",
                beam_size=1,
                best_of=1,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            segment_texts = [segment.text.strip() for segment in segments if segment.text and segment.text.strip()]
        except Exception as exc:
            raise AudioTranscriptionError(f"falha na transcricao: {exc}") from exc

        text = " ".join(segment_texts).strip()
        if not text:
            text = "(sem fala detectada)"

        if duration_seconds is None:
            info_duration = getattr(info, "duration", None)
            if isinstance(info_duration, (float, int)) and info_duration > 0:
                duration_seconds = float(info_duration)

        if (
            isinstance(duration_seconds, (int, float))
            and max_duration_seconds > 0
            and duration_seconds > max_duration_seconds
        ):
            raise AudioTooLongError(float(duration_seconds), max_duration_seconds)

        detected_language = getattr(info, "language", None)
        if isinstance(detected_language, str):
            detected_language = detected_language.strip() or None
        else:
            detected_language = None

        return AudioTranscription(
            text=text,
            duration_seconds=duration_seconds if isinstance(duration_seconds, (int, float)) else None,
            detected_language=detected_language,
        )
