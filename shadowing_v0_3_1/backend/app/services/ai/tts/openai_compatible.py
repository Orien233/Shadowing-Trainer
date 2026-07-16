from typing import Any

import httpx

from app.services.ai.audio_types import AudioCapability, TTSResult
from app.services.ai.tts.base import TTSProvider, TTSRequest


class OpenAICompatibleTTSProvider(TTSProvider):
    """Adapter for the OpenAI Audio Speech API request shape."""
    capabilities = frozenset({AudioCapability.SYNTHESIZE})
    def __init__(self, *, base_url: str, api_key: str, model_name: str, extra_config: dict[str, Any] | None = None) -> None:
        self.base_url, self.api_key, self.model_name = base_url.rstrip("/"), api_key, model_name
        self.extra_config = extra_config or {}

    def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self.api_key:
            raise ValueError("Provider API key is not configured.")
        payload: dict[str, Any] = {"model": request.model or self.model_name, "input": request.text, "voice": request.voice or self.extra_config.get("default_voice", "alloy"), "speed": request.speed}
        response_format = self.extra_config.get("response_format")
        if response_format:
            payload["response_format"] = response_format
        # The configured URL is the full synthesis endpoint. Compatible
        # providers often expose a different path, so never append /audio/speech.
        response = httpx.post(self.base_url, json=payload, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=120)
        response.raise_for_status()
        if not response.content:
            raise ValueError("TTS provider returned an empty audio file.")
        response_format = str(payload.get("response_format", "mp3")).lower()
        extension = {"mp3": "mp3", "wav": "wav", "opus": "opus", "aac": "aac", "flac": "flac", "pcm": "pcm"}.get(response_format, "mp3")
        return TTSResult(audio=response.content, media_type=response.headers.get("content-type", "audio/mpeg"), extension=extension, provider_metadata={"adapter": "openai_audio", "model": payload["model"]})

    def list_voices(self) -> list[dict[str, Any]]:
        voices = self.extra_config.get("voices", [])
        return voices if isinstance(voices, list) else []

    def test_connection(self) -> str:
        self.synthesize(TTSRequest(text="Connection test.", voice=self.extra_config.get("default_voice")))
        return "TTS connection succeeded."
