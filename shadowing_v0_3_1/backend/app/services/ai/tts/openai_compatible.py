from typing import Any

import httpx

from app.services.ai.tts.base import TTSProvider, TTSRequest


class OpenAICompatibleTTSProvider(TTSProvider):
    def __init__(self, *, base_url: str, api_key: str, model_name: str, extra_config: dict[str, Any] | None = None) -> None:
        self.base_url, self.api_key, self.model_name = base_url.rstrip("/"), api_key, model_name
        self.extra_config = extra_config or {}

    def synthesize(self, request: TTSRequest) -> bytes:
        if not self.api_key:
            raise ValueError("Provider API key is not configured.")
        payload: dict[str, Any] = {"model": request.model or self.model_name, "input": request.text, "voice": request.voice or self.extra_config.get("default_voice", "alloy"), "speed": request.speed}
        response_format = self.extra_config.get("response_format")
        if response_format:
            payload["response_format"] = response_format
        response = httpx.post(f"{self.base_url}/audio/speech", json=payload, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=120)
        response.raise_for_status()
        if not response.content:
            raise ValueError("TTS provider returned an empty audio file.")
        return response.content

    def list_voices(self) -> list[dict[str, Any]]:
        voices = self.extra_config.get("voices", [])
        return voices if isinstance(voices, list) else []

    def test_connection(self) -> str:
        self.synthesize(TTSRequest(text="Connection test.", voice=self.extra_config.get("default_voice")))
        return "TTS connection succeeded."
