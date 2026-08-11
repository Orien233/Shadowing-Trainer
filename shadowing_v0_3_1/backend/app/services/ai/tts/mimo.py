from __future__ import annotations

import base64
from typing import Any

from app.services.ai.http_transport import provider_http
from app.services.ai.audio_types import AudioCapability, TTSResult
from app.services.ai.audio_utils import (
    configuration_message,
    extension_from_format,
    normalized_voices,
    raw_pcm_from_config,
)
from app.services.ai.tts.base import TTSProvider, TTSRequest


_MEDIA_TYPES = {
    "wav": "audio/wav", "mp3": "audio/mpeg", "pcm16": "audio/L16",
    "opus": "audio/opus", "flac": "audio/flac",
}


class MiMoTTSProvider(TTSProvider):
    """Adapter for MiMo V2.5 TTS Chat Completions API.

    MiMo's speech synthesis is not the OpenAI ``/audio/speech`` endpoint:
    text is an assistant message and audio is returned Base64-encoded inside a
    chat completion. ``base_url`` is intentionally the full chat-completions
    endpoint supplied by the user.
    """

    capabilities = frozenset({AudioCapability.SYNTHESIZE})

    def __init__(self, base_url: str, api_key: str, model_name: str, extra_config: dict[str, Any] | None = None) -> None:
        self.base_url, self.api_key, self.model_name = base_url.rstrip("/"), api_key, model_name
        self.extra_config = extra_config or {}

    def _headers(self) -> dict[str, str]:
        if self.extra_config.get("auth_scheme") == "api-key":
            return {"api-key": self.api_key, "Content-Type": "application/json"}
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _instruction(self, request: TTSRequest) -> str | None:
        parts = [str(self.extra_config.get("style_instruction", "")).strip()]
        if request.accent:
            parts.append(f"Accent: {request.accent}.")
        if request.gender:
            parts.append(f"Voice gender: {request.gender}.")
        if request.speed != 1.0:
            parts.append(f"Speak at {request.speed:.2f}x speed.")
        instruction = " ".join(part for part in parts if part)
        return instruction or None

    def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self.api_key:
            raise ValueError("Provider API key is not configured.")
        audio_format = str(self.extra_config.get("audio_format", "wav")).lower()
        raw_pcm = (
            raw_pcm_from_config(self.extra_config, provider_name="MiMo TTS")
            if audio_format == "pcm16"
            else None
        )
        messages: list[dict[str, str]] = []
        if instruction := self._instruction(request):
            messages.append({"role": "user", "content": instruction})
        messages.append({"role": "assistant", "content": request.text})
        payload = {
            "model": request.model or self.model_name,
            "messages": messages,
            "audio": {"format": audio_format, "voice": request.voice or self.extra_config.get("default_voice", "mimo_default")},
        }
        response = provider_http.post(self.base_url, json=payload, headers=self._headers(), timeout=120)
        response.raise_for_status()
        data = response.json()
        try:
            encoded = data["choices"][0]["message"]["audio"]["data"]
            audio = base64.b64decode(encoded, validate=True)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError("MiMo TTS response did not contain valid Base64 audio data.") from exc
        if not audio:
            raise ValueError("MiMo TTS returned empty audio data.")
        extension = extension_from_format(audio_format)
        return TTSResult(audio=audio, media_type=_MEDIA_TYPES.get(audio_format, "application/octet-stream"), extension=extension, raw_pcm=raw_pcm, provider_metadata={"adapter": "mimo_tts", "model": payload["model"], "voice": payload["audio"]["voice"]})

    def list_voices(self) -> list[dict[str, Any]]:
        return normalized_voices(self.extra_config.get("voices", []))

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="MiMo TTS",
        )
