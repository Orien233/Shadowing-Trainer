from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.services.local_whisper_runtime import load_local_whisper_model

# transcribe the audio using the Whisper model, returning a list of segments with start time, end time, and text
def get_model() -> Any:
    """Compatibility entry point backed by the optional Whisper runtime."""
    return load_local_whisper_model()


def _serialize_word_timestamps(words: Iterable[Any] | None) -> List[Dict[str, Any]]:
    if not words:
        return []

    serialized_words: List[Dict[str, Any]] = []
    for word in words:
        raw_start = getattr(word, "start", None)
        raw_end = getattr(word, "end", None)
        raw_text = getattr(word, "word", "")
        serialized_words.append(
            {
                "start": float(raw_start) if raw_start is not None else None,
                "end": float(raw_end) if raw_end is not None else None,
                "word": str(raw_text).strip(),
            }
        )
    return serialized_words


def transcribe_audio(audio_path: str, *, word_timestamps: bool = False) -> List[Dict[str, Any]]:
    model = get_model()
    segments, _info = model.transcribe(
        audio_path,
        vad_filter=True,
        word_timestamps=word_timestamps,
    )
    results: List[Dict[str, Any]] = []
    for segment in segments:
        results.append(
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text.strip(),
                "words": _serialize_word_timestamps(getattr(segment, "words", None)),
            }
        )
    return results


def transcribe_audio_with_word_timestamps(audio_path: str) -> List[Dict[str, Any]]:
    return transcribe_audio(audio_path, word_timestamps=True)


# transcribe the audio and return the full text as a single string
def transcribe_text(audio_path: str) -> str:
    segments = transcribe_audio(audio_path)
    return " ".join(seg["text"] for seg in segments).strip()
