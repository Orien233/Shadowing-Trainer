from typing import Any

from app.services.ai.asr.base import ASRProvider
from app.services.ai.audio_types import ASRResult, ASRSegment, ASRWord, AudioCapability
from app.services.local_whisper_runtime import get_local_whisper_status, LocalWhisperUnavailableError
from app.services.transcription_service import transcribe_audio


class LocalWhisperASRProvider(ASRProvider):
    """Thin provider wrapper retaining the cached faster-whisper model."""

    capabilities = frozenset({AudioCapability.TRANSCRIBE, AudioCapability.WORD_TIMESTAMPS})

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model_name: str = "",
        extra_config: dict[str, Any] | None = None,
    ) -> None:
        # These fields are accepted for uniform adapter construction.  Local
        # Whisper intentionally ignores remote credentials and model names.
        self.base_url = base_url
        self.api_key = api_key
        self.model_name = model_name
        self.extra_config = dict(extra_config or {})

    def transcribe(self, audio_path: str, *, word_timestamps: bool = False) -> ASRResult:
        if word_timestamps:
            self.require(AudioCapability.WORD_TIMESTAMPS)
        raw_segments = transcribe_audio(audio_path, word_timestamps=word_timestamps)
        segments = [
            ASRSegment(
                text=str(item.get("text", "")).strip(),
                start=float(item.get("start", 0.0)), end=float(item.get("end", 0.0)),
                words=[ASRWord(text=str(word.get("word", "")).strip(), start=word.get("start"), end=word.get("end")) for word in item.get("words", [])],
            ) for item in raw_segments
        ]
        return ASRResult(text=" ".join(item.text for item in segments).strip(), segments=segments, provider_metadata={"adapter": "local_whisper"})

    def test_connection(self) -> str:
        # Loading only happens when first transcribing, preserving lazy model startup.
        status = get_local_whisper_status()
        if not status.runtime_ready:
            raise LocalWhisperUnavailableError(status.error or "Local Whisper is unavailable.")
        if status.model_loaded:
            return "Local Whisper is loaded and ready."
        if status.model_cached:
            return "Local Whisper is installed; its cached model will load on first transcription."
        if status.will_download_on_first_use:
            return "Local Whisper is installed; its model will download and load on first transcription."
        return "Local Whisper is installed and ready to load on first transcription."
