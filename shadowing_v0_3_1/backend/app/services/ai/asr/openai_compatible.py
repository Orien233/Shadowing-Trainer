from pathlib import Path
from typing import Any

import httpx

from app.services.ai.asr.base import ASRProvider
from app.services.ai.audio_types import ASRResult, ASRSegment, ASRWord, AudioCapability


class OpenAICompatibleRemoteASRProvider(ASRProvider):
    """Adapter for the OpenAI Audio Transcriptions API request shape."""
    capabilities = frozenset({AudioCapability.TRANSCRIBE, AudioCapability.WORD_TIMESTAMPS})
    def __init__(self, *, base_url: str, api_key: str, model_name: str, extra_config: dict[str, Any] | None = None) -> None:
        self.base_url, self.api_key, self.model_name = base_url.rstrip("/"), api_key, model_name
        self.extra_config = extra_config or {}

    def transcribe(self, audio_path: str, *, word_timestamps: bool = False) -> ASRResult:
        if not self.api_key:
            raise ValueError("Provider API key is not configured.")
        if word_timestamps:
            self.require(AudioCapability.WORD_TIMESTAMPS)
        path = Path(audio_path)
        data: dict[str, str] = {"model": self.model_name, "response_format": "verbose_json"}
        if word_timestamps:
            data["timestamp_granularities[]"] = "word"
        with path.open("rb") as audio_file:
            response = httpx.post(f"{self.base_url}/audio/transcriptions", data=data, files={"file": (path.name, audio_file, "application/octet-stream")}, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=120)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("ASR provider returned an invalid response.")
        segments = payload.get("segments")
        if isinstance(segments, list):
            all_words = payload.get("words") if isinstance(payload.get("words"), list) else []
            normalized_segments: list[ASRSegment] = []
            for item in segments:
                if not isinstance(item, dict):
                    continue
                start, end = float(item.get("start", 0)), float(item.get("end", 0))
                words = [ASRWord(text=str(word.get("word", "")).strip(), start=word.get("start"), end=word.get("end")) for word in all_words if isinstance(word, dict) and float(word.get("start", 0)) >= start and float(word.get("end", 0)) <= end]
                normalized_segments.append(ASRSegment(text=str(item.get("text", "")).strip(), start=start, end=end, words=words))
            return ASRResult(text=str(payload.get("text", "")).strip() or " ".join(item.text for item in normalized_segments).strip(), segments=normalized_segments, provider_metadata={"adapter": "openai_audio"})
        text = str(payload.get("text", "")).strip()
        return ASRResult(text=text, segments=[ASRSegment(text=text)] if text else [], provider_metadata={"adapter": "openai_audio"})

    def test_connection(self) -> str:
        if not self.api_key:
            raise ValueError("Provider API key is not configured.")
        response = httpx.get(
            f"{self.base_url}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=20,
        )
        response.raise_for_status()
        return "Remote ASR connection succeeded."
