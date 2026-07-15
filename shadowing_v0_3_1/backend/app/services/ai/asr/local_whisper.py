from app.services.ai.asr.base import ASRProvider
from app.services.transcription_service import transcribe_audio


class LocalWhisperASRProvider(ASRProvider):
    """Thin provider wrapper retaining the cached faster-whisper model."""

    def transcribe(self, audio_path: str, *, word_timestamps: bool = False) -> list[dict]:
        return transcribe_audio(audio_path, word_timestamps=word_timestamps)

    def test_connection(self) -> str:
        # Loading only happens when first transcribing, preserving lazy model startup.
        return "Local Whisper is available and will load on first transcription."
