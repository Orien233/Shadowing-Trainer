from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List

from faster_whisper import WhisperModel

from app.core.config import settings

# transcribe the audio using the Whisper model, returning a list of segments with start time, end time, and text
@lru_cache(maxsize=1)
def get_model() -> WhisperModel:
    return WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )

# --- IGNORE ---
def transcribe_audio(audio_path: str) -> List[Dict[str, Any]]:
    model = get_model()
    segments, _info = model.transcribe(audio_path, vad_filter=True, word_timestamps=False)
    results: List[Dict[str, Any]] = []
    for segment in segments:
        results.append(
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text.strip(),
            }
        )
    return results

# transcribe the audio and return the full text as a single string
def transcribe_text(audio_path: str) -> str:
    segments = transcribe_audio(audio_path)
    return " ".join(seg["text"] for seg in segments).strip()
