"""DashScope speech-synthesis adapter."""

from __future__ import annotations

import base64
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


def _generation_endpoint(base_url: str, extra_config: dict[str, Any]) -> str:
    explicit = extra_config.get("endpoint")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.rstrip("/")
    url = base_url.rstrip("/")
    if url.endswith("/generation"):
        return url
    if url.endswith("/api/v1"):
        return f"{url}/services/aigc/multimodal-generation/generation"
    return f"{url}/api/v1/services/aigc/multimodal-generation/generation"


class DashScopeTTSProvider(TTSProvider):
    """DashScope non-streaming TTS, including URL and Base64 audio responses."""

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
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        configured = self.extra_config.get("headers")
        if isinstance(configured, dict):
            headers.update({str(key): str(value) for key, value in configured.items()})
        return headers

    def _payload(self, request: TTSRequest, audio_format: str) -> dict[str, Any]:
        voice = request.voice or self.extra_config.get("default_voice", "Cherry")
        input_body: dict[str, Any] = {"text": request.text, "voice": voice}
        language = request.accent or self.extra_config.get("language") or self.extra_config.get("language_type")
        if language:
            input_body["language_type"] = language
        parameters = self.extra_config.get("parameters")
        options = dict(parameters) if isinstance(parameters, dict) else {}
        options.setdefault("format", audio_format)
        if request.speed != 1.0:
            options.setdefault("speed", request.speed)
        return {"model": request.model or self.model_name, "input": input_body, "parameters": options}

    def synthesize(self, request: TTSRequest) -> TTSResult:
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="DashScope TTS",
        )
        audio_format = str(self.extra_config.get("audio_format", self.extra_config.get("format", "mp3")))
        response = provider_http.post(
            _generation_endpoint(self.base_url, self.extra_config),
            json=self._payload(request, audio_format),
            headers=self._headers(),
            timeout=float(self.extra_config.get("timeout", 120)),
        )
        response.raise_for_status()
        audio, content_type = self._audio_from_response(response)
        if not audio:
            raise ValueError("DashScope TTS response did not contain audio data.")
        extension = extension_from_format(audio_format)
        return TTSResult(
            audio=audio,
            media_type=content_type or media_type_for_extension(extension),
            extension=extension,
            provider_metadata={"adapter": "dashscope_tts", "model": request.model or self.model_name},
        )

    def _audio_from_response(self, response: Any) -> tuple[bytes, str | None]:
        try:
            payload = as_mapping(response.json())
        except (AttributeError, ValueError):
            audio = getattr(response, "content", b"")
            return audio, response_media_type(response, "") or None
        output = as_mapping(payload.get("output"))
        audio_value: Any = output.get("audio") or output.get("audio_url")
        if not audio_value:
            choices = as_list(output.get("choices"))
            if choices:
                message = as_mapping(as_mapping(choices[0]).get("message"))
                for content in as_list(message.get("content")):
                    item = as_mapping(content)
                    audio_value = item.get("audio") or item.get("audio_url") or item.get("url") or audio_value
                    if audio_value:
                        break
        if isinstance(audio_value, dict):
            audio_value = audio_value.get("data") or audio_value.get("url") or audio_value.get("audio_url")
        if isinstance(audio_value, str) and audio_value.startswith(("https://", "http://")):
            download = provider_http.get(audio_value, timeout=float(self.extra_config.get("timeout", 120)))
            download.raise_for_status()
            return getattr(download, "content", b""), response_media_type(download, "") or None
        if isinstance(audio_value, str) and audio_value:
            encoded = audio_value.rsplit(",", 1)[-1]
            try:
                return base64.b64decode(encoded, validate=True), None
            except ValueError:
                pass
        return b"", None

    def list_voices(self) -> list[dict[str, Any]]:
        return normalized_voices(self.extra_config.get("voices", []))

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="DashScope TTS",
        )
