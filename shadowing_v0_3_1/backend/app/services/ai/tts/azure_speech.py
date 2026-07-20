"""Azure Speech synthesis adapter."""

from __future__ import annotations

from html import escape
from typing import Any

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


def _synthesis_endpoint(base_url: str, extra_config: dict[str, Any]) -> str:
    explicit = extra_config.get("endpoint")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.rstrip("/")
    url = base_url.rstrip("/")
    if url.endswith("/cognitiveservices/v1"):
        return url
    return f"{url}/cognitiveservices/v1"


def _voices_endpoint(base_url: str, extra_config: dict[str, Any]) -> str:
    explicit = extra_config.get("voices_endpoint")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.rstrip("/")
    url = base_url.rstrip("/")
    if url.endswith("/cognitiveservices/v1"):
        url = url[: -len("/cognitiveservices/v1")]
    return f"{url}/cognitiveservices/voices/list"


class AzureSpeechTTSProvider(TTSProvider):
    """Azure Speech SSML adapter with format-aware file extensions."""

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

    def _headers(self, *, ssml: bool = False) -> dict[str, str]:
        if str(self.extra_config.get("auth_scheme", "")).lower() == "bearer":
            headers = {"Authorization": f"Bearer {self.api_key}"}
        else:
            headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        if ssml:
            headers["Content-Type"] = "application/ssml+xml"
            headers["X-Microsoft-OutputFormat"] = str(
                self.extra_config.get("output_format", "audio-24khz-48kbitrate-mono-mp3")
            )
        configured = self.extra_config.get("headers")
        if isinstance(configured, dict):
            headers.update({str(key): str(value) for key, value in configured.items()})
        return headers

    def synthesize(self, request: TTSRequest) -> TTSResult:
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="Azure Speech TTS",
        )
        voice = request.voice or str(self.extra_config.get("default_voice") or self.model_name)
        locale = request.accent or str(self.extra_config.get("locale", "en-US"))
        rate = f"{round((request.speed - 1) * 100):+d}%"
        ssml = (
            f'<speak version="1.0" xml:lang="{escape(locale, quote=True)}">'
            f'<voice name="{escape(voice, quote=True)}"><prosody rate="{rate}">'
            f"{escape(request.text)}</prosody></voice></speak>"
        )
        output_format = str(self.extra_config.get("output_format", "audio-24khz-48kbitrate-mono-mp3"))
        response = provider_http.post(
            _synthesis_endpoint(self.base_url, self.extra_config),
            content=ssml.encode("utf-8"),
            headers=self._headers(ssml=True),
            timeout=float(self.extra_config.get("timeout", 120)),
        )
        response.raise_for_status()
        audio = getattr(response, "content", b"")
        if not audio:
            raise ValueError("Azure Speech TTS returned an empty audio file.")
        extension = extension_from_format(output_format)
        return TTSResult(
            audio=audio,
            media_type=response_media_type(response, media_type_for_extension(extension)),
            extension=extension,
            provider_metadata={"adapter": "azure_speech_tts", "voice": voice, "output_format": output_format},
        )

    def list_voices(self) -> list[dict[str, Any]]:
        if "voices" in self.extra_config:
            return normalized_voices(self.extra_config.get("voices"))
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="Azure Speech TTS",
        )
        response = provider_http.get(
            _voices_endpoint(self.base_url, self.extra_config),
            headers=self._headers(),
            timeout=float(self.extra_config.get("timeout", 30)),
        )
        response.raise_for_status()
        payload = response.json()
        records = as_list(payload)
        if not records:
            records = as_list(as_mapping(payload).get("voices"))
        return normalized_voices(records)

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="Azure Speech TTS",
        )
