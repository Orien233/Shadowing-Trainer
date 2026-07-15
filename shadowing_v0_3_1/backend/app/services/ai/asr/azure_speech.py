from pathlib import Path
from typing import Any

import httpx

from app.services.ai.asr.base import ASRProvider
from app.services.ai.audio_types import ASRResult, ASRSegment, AudioCapability


class AzureSpeechASRProvider(ASRProvider):
    """Azure Speech adapter behind the project's OpenAI-shaped audio contract."""
    capabilities = frozenset({AudioCapability.TRANSCRIBE})

    def __init__(self, *, base_url: str, api_key: str, model_name: str, extra_config: dict[str, Any] | None = None) -> None:
        self.base_url, self.api_key, self.model_name = base_url.rstrip("/"), api_key, model_name
        self.extra_config = extra_config or {}

    def transcribe(self, audio_path: str, *, word_timestamps: bool = False) -> ASRResult:
        if not self.api_key:
            raise ValueError("Provider API key is not configured.")
        if word_timestamps:
            self.require(AudioCapability.WORD_TIMESTAMPS)
        path = Path(audio_path)
        language = self.extra_config.get("language", "en-US")
        endpoint = f"{self.base_url}/speech/recognition/conversation/cognitiveservices/v1"
        with path.open("rb") as audio_file:
            response = httpx.post(endpoint, params={"language": language, "format": "detailed"}, content=audio_file.read(), headers={"Ocp-Apim-Subscription-Key": self.api_key, "Content-Type": "audio/wav"}, timeout=120)
        response.raise_for_status()
        payload = response.json()
        text = str(payload.get("DisplayText", "")).strip()
        duration = float(payload.get("Duration", 0)) / 10_000_000
        return ASRResult(text=text, segments=[ASRSegment(text=text, start=0.0, end=duration)] if text else [], provider_metadata={"adapter": "azure_speech", "recognition_status": payload.get("RecognitionStatus")})

    def test_connection(self) -> str:
        if not self.api_key:
            raise ValueError("Provider API key is not configured.")
        return "Azure Speech ASR is configured. Submit audio to test transcription."
