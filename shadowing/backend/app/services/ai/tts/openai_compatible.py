"""OpenAI Audio Speech adapters."""

from __future__ import annotations

from typing import Any

from app.services.ai.http_transport import provider_http
from app.services.ai.audio_types import AudioCapability, TTSResult
from app.services.ai.audio_utils import (
    configuration_message,
    extension_from_format,
    extension_from_media_type,
    media_type_for_extension,
    normalized_voices,
    raw_pcm_from_config,
    require_configured,
    response_media_type,
)
from app.services.ai.tts.base import TTSProvider, TTSRequest


class OpenAIAudioTTSProvider(TTSProvider):
    """Native OpenAI Audio Speech adapter using a user-provided full endpoint."""

    capabilities = frozenset({AudioCapability.SYNTHESIZE})

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        extra_config: dict[str, Any] | None = None,
    ) -> None:
        # Do not append ``/audio/speech``: the catalog intentionally stores the
        # exact endpoint so compatible proxies can use their own paths.
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.extra_config = dict(extra_config or {})

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        configured = self.extra_config.get("headers")
        if isinstance(configured, dict):
            headers.update({str(key): str(value) for key, value in configured.items()})
        return headers

    def synthesize(self, request: TTSRequest) -> TTSResult:
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="OpenAI Audio TTS",
        )
        response_format = str(self.extra_config.get("response_format", "mp3"))
        raw_pcm = (
            raw_pcm_from_config(
                self.extra_config,
                # Native OpenAI PCM is 24 kHz mono signed 16-bit little-endian.
                # Compatible endpoints may override every value below.
                default_sample_rate=24000,
                provider_name="OpenAI Audio TTS",
            )
            if response_format.strip().lower() == "pcm"
            else None
        )
        payload: dict[str, Any] = {
            "model": request.model or self.model_name,
            "input": request.text,
            "voice": request.voice or self.extra_config.get("default_voice", "alloy"),
            "speed": request.speed,
            "response_format": response_format,
        }
        instructions = self.extra_config.get("instructions") or self.extra_config.get("style_instruction")
        if instructions:
            # This setting was explicitly chosen by the user for an endpoint
            # which accepts OpenAI's optional instructions field.
            payload["instructions"] = str(instructions)
        # ``language`` is deliberately internal metadata by default.  Many
        # OpenAI-compatible speech endpoints implement only the base request
        # shape and reject unfamiliar optional fields.  Users can opt in only
        # after confirming their endpoint implements ``instructions``.
        if request.language and self.extra_config.get("send_language_instruction") is True:
            language_instruction = f"Speak the input in {request.language}."
            payload["instructions"] = " ".join(
                part for part in (str(payload.get("instructions", "")).strip(), language_instruction) if part
            )
        response = provider_http.post(
            self.base_url,
            json=payload,
            headers=self._headers(),
            timeout=float(self.extra_config.get("timeout", 120)),
        )
        response.raise_for_status()
        audio = getattr(response, "content", b"")
        if not audio:
            raise ValueError("OpenAI Audio TTS returned an empty audio file.")
        extension = extension_from_format(response_format)
        media_type = response_media_type(response, media_type_for_extension(extension))
        if response_format == "":
            extension = extension_from_media_type(media_type, extension)
        return TTSResult(
            audio=audio,
            media_type=media_type,
            extension=extension,
            raw_pcm=raw_pcm,
            provider_metadata={"adapter": "openai_audio_tts", "model": payload["model"], "voice": payload["voice"], "language": request.language},
        )

    def list_voices(self) -> list[dict[str, Any]]:
        # OpenAI's built-in voice list is static, while custom voices depend on
        # account access.  Configuration keeps this endpoint-free.
        return normalized_voices(self.extra_config.get("voices", []))

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="OpenAI Audio TTS",
        )


class OpenAICompatibleTTSProvider(OpenAIAudioTTSProvider):
    """Backward-compatible class name for legacy OpenAI-compatible records."""
