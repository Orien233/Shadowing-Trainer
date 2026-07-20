"""Deepgram Aura text-to-speech adapter."""

from __future__ import annotations

from typing import Any

from app.services.ai.http_transport import provider_http
from app.services.ai.audio_types import AudioCapability, TTSResult
from app.services.ai.audio_utils import (
    configuration_message,
    extension_from_format,
    media_type_for_extension,
    normalized_voices,
    require_configured,
    response_media_type,
)
from app.services.ai.tts.base import TTSProvider, TTSRequest


def _speak_endpoint(base_url: str, extra_config: dict[str, Any]) -> str:
    explicit = extra_config.get("endpoint")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.rstrip("/")
    url = base_url.rstrip("/")
    if url.endswith("/speak"):
        return url
    if url.endswith("/v1"):
        return f"{url}/speak"
    return f"{url}/v1/speak"


class DeepgramTTSProvider(TTSProvider):
    """Deepgram Aura TTS.  Deepgram's voice is selected by its model name."""

    capabilities = frozenset({AudioCapability.SYNTHESIZE})

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
        headers = {"Authorization": f"Token {self.api_key}", "Content-Type": "application/json"}
        configured = self.extra_config.get("headers")
        if isinstance(configured, dict):
            headers.update({str(key): str(value) for key, value in configured.items()})
        return headers

    def _params(self, request: TTSRequest) -> dict[str, Any]:
        params: dict[str, Any] = {"model": request.model or request.voice or self.model_name}
        for key in ("encoding", "container", "sample_rate", "bit_rate", "callback", "callback_method"):
            value = self.extra_config.get(key)
            if value is not None:
                params[key] = value
        if request.speed != 1.0:
            params["speed"] = request.speed
        configured = self.extra_config.get("parameters")
        if isinstance(configured, dict):
            params.update(configured)
        return params

    def synthesize(self, request: TTSRequest) -> TTSResult:
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="Deepgram TTS",
        )
        params = self._params(request)
        response = provider_http.post(
            _speak_endpoint(self.base_url, self.extra_config),
            params=params,
            json={"text": request.text},
            headers=self._headers(),
            timeout=float(self.extra_config.get("timeout", 120)),
        )
        response.raise_for_status()
        audio = getattr(response, "content", b"")
        if not audio:
            raise ValueError("Deepgram TTS returned an empty audio file.")
        extension = extension_from_format(params.get("container") or params.get("encoding") or "mp3")
        return TTSResult(
            audio=audio,
            media_type=response_media_type(response, media_type_for_extension(extension)),
            extension=extension,
            provider_metadata={"adapter": "deepgram_tts", "model": params["model"]},
        )

    def list_voices(self) -> list[dict[str, Any]]:
        return normalized_voices(self.extra_config.get("voices", []))

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="Deepgram TTS",
        )
