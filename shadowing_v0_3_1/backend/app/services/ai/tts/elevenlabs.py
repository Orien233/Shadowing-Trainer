"""ElevenLabs text-to-speech adapter."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.services.ai.http_transport import provider_http
from app.services.ai.audio_types import AudioCapability, TTSResult
from app.services.ai.audio_utils import (
    as_list,
    as_mapping,
    configuration_message,
    extension_from_format,
    media_type_for_extension,
    normalized_voices,
    require_configured,
    response_media_type,
)
from app.services.ai.tts.base import TTSProvider, TTSRequest


def _voice_id(request: TTSRequest, extra_config: dict[str, Any]) -> str:
    value = request.voice or extra_config.get("default_voice") or extra_config.get("voice_id")
    return str(value).strip() if value else ""


def _synthesis_endpoint(base_url: str, voice_id: str, extra_config: dict[str, Any]) -> str:
    template = extra_config.get("endpoint_template") or base_url
    if not isinstance(template, str) or not template.strip():
        return ""
    url = template.rstrip("/")
    encoded_voice = quote(voice_id, safe="")
    if "{voice_id}" in url:
        if not encoded_voice:
            raise ValueError("ElevenLabs TTS requires a voice ID.")
        return url.replace("{voice_id}", encoded_voice)
    if "/text-to-speech/" in url:
        # A full provider endpoint already names a voice and is authoritative.
        return url
    if not encoded_voice:
        raise ValueError("ElevenLabs TTS requires a voice ID in the request or configuration.")
    if url.endswith("/text-to-speech"):
        return f"{url}/{encoded_voice}"
    if url.endswith("/v1"):
        return f"{url}/text-to-speech/{encoded_voice}"
    return f"{url}/v1/text-to-speech/{encoded_voice}"


def _voices_endpoint(base_url: str, extra_config: dict[str, Any]) -> str:
    explicit = extra_config.get("voices_endpoint")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.rstrip("/")
    url = base_url.rstrip("/")
    marker = "/v1/text-to-speech"
    if marker in url:
        return f"{url.split(marker, 1)[0]}/v1/voices"
    if url.endswith("/v1"):
        return f"{url}/voices"
    return f"{url}/v1/voices"


class ElevenLabsTTSProvider(TTSProvider):
    """ElevenLabs TTS with an endpoint template or a configured default voice."""

    capabilities = frozenset({AudioCapability.SYNTHESIZE, AudioCapability.LIST_VOICES})

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        extra_config: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.extra_config = dict(extra_config or {})

    def _headers(self) -> dict[str, str]:
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        configured = self.extra_config.get("headers")
        if isinstance(configured, dict):
            headers.update({str(key): str(value) for key, value in configured.items()})
        return headers

    def _params(self, output_format: str) -> dict[str, Any]:
        params: dict[str, Any] = {"output_format": output_format}
        for key in ("enable_logging", "optimize_streaming_latency", "apply_text_normalization"):
            value = self.extra_config.get(key)
            if value is not None:
                params[key] = value
        configured = self.extra_config.get("parameters")
        if isinstance(configured, dict):
            params.update(configured)
        return params

    def synthesize(self, request: TTSRequest) -> TTSResult:
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="ElevenLabs TTS",
        )
        voice = _voice_id(request, self.extra_config)
        output_format = str(self.extra_config.get("output_format", "mp3_44100_128"))
        voice_settings = self.extra_config.get("voice_settings")
        payload: dict[str, Any] = {"text": request.text, "model_id": request.model or self.model_name}
        if isinstance(voice_settings, dict):
            payload["voice_settings"] = voice_settings
        language_code = self.extra_config.get("language_code") or self.extra_config.get("language")
        if language_code:
            payload["language_code"] = str(language_code)
        response = provider_http.post(
            _synthesis_endpoint(self.base_url, voice, self.extra_config),
            params=self._params(output_format),
            json=payload,
            headers=self._headers(),
            timeout=float(self.extra_config.get("timeout", 120)),
        )
        response.raise_for_status()
        audio = getattr(response, "content", b"")
        if not audio:
            raise ValueError("ElevenLabs TTS returned an empty audio file.")
        extension = extension_from_format(output_format)
        return TTSResult(
            audio=audio,
            media_type=response_media_type(response, media_type_for_extension(extension)),
            extension=extension,
            provider_metadata={"adapter": "elevenlabs_tts", "model": payload["model_id"], "voice": voice or None},
        )

    def list_voices(self) -> list[dict[str, Any]]:
        if "voices" in self.extra_config:
            return normalized_voices(self.extra_config.get("voices"))
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="ElevenLabs TTS",
        )
        response = provider_http.get(
            _voices_endpoint(self.base_url, self.extra_config),
            headers=self._headers(),
            timeout=float(self.extra_config.get("timeout", 30)),
        )
        response.raise_for_status()
        payload = as_mapping(response.json())
        return normalized_voices(as_list(payload.get("voices")))

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="ElevenLabs TTS",
        )
