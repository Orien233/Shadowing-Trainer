from html import escape
from typing import Any

import httpx

from app.services.ai.audio_types import AudioCapability, TTSResult
from app.services.ai.tts.base import TTSProvider, TTSRequest


class AzureSpeechTTSProvider(TTSProvider):
    """Azure Speech SSML adapter behind the project TTS result contract."""
    capabilities = frozenset({AudioCapability.SYNTHESIZE})

    def __init__(self, *, base_url: str, api_key: str, model_name: str, extra_config: dict[str, Any] | None = None) -> None:
        self.base_url, self.api_key, self.model_name = base_url.rstrip("/"), api_key, model_name
        self.extra_config = extra_config or {}

    def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self.api_key:
            raise ValueError("Provider API key is not configured.")
        voice = request.voice or self.extra_config.get("default_voice") or self.model_name
        locale = request.accent or self.extra_config.get("locale", "en-US")
        rate = f"{round((request.speed - 1) * 100):+d}%"
        ssml = f'<speak version="1.0" xml:lang="{escape(locale)}"><voice name="{escape(voice)}"><prosody rate="{rate}">{escape(request.text)}</prosody></voice></speak>'
        response = httpx.post(f"{self.base_url}/cognitiveservices/v1", content=ssml.encode("utf-8"), headers={"Ocp-Apim-Subscription-Key": self.api_key, "Content-Type": "application/ssml+xml", "X-Microsoft-OutputFormat": self.extra_config.get("output_format", "audio-24khz-48kbitrate-mono-mp3")}, timeout=120)
        response.raise_for_status()
        if not response.content:
            raise ValueError("Azure Speech returned an empty audio file.")
        return TTSResult(audio=response.content, media_type=response.headers.get("content-type", "audio/mpeg"), extension="mp3", provider_metadata={"adapter": "azure_speech", "voice": voice})

    def list_voices(self) -> list[dict[str, Any]]:
        return []

    def test_connection(self) -> str:
        self.synthesize(TTSRequest(text="Connection test."))
        return "Azure Speech TTS connection succeeded."
