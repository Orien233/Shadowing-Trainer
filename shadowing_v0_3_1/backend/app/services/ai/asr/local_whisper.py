from app.services.ai.asr.base import ASRProvider
from app.services.ai.audio_types import ASRResult, ASRSegment, ASRWord, AudioCapability
from app.services.transcription_service import transcribe_audio


class LocalWhisperASRProvider(ASRProvider):
    """Thin provider wrapper retaining the cached faster-whisper model."""

    capabilities = frozenset({AudioCapability.TRANSCRIBE, AudioCapability.WORD_TIMESTAMPS})

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
        return "Local Whisper is available and will load on first transcription."
