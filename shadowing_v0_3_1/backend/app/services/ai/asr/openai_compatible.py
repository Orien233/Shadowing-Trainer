"""OpenAI-shaped speech-to-text adapters.

OpenAI's Whisper verbose response can provide word timing data, whereas modern
GPT transcription models and arbitrary OpenAI-compatible gateways cannot be
assumed to do so.  They are deliberately represented by separate adapters so
scene capability checks remain truthful before any audio is uploaded.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from app.services.ai.http_transport import provider_http
from app.services.ai.asr._helpers import openai_verbose_result
from app.services.ai.asr.base import ASRProvider, openai_language_code, resolve_asr_language
from app.services.ai.audio_types import ASRResult, ASRSegment, AudioCapability
from app.services.ai.audio_utils import as_mapping, configuration_message, require_configured


def _native_transcriptions_endpoint(base_url: str, extra_config: dict[str, Any]) -> str:
    """Resolve OpenAI's transcription endpoint while accepting a full URL."""
    explicit = extra_config.get("endpoint")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.rstrip("/")
    url = base_url.rstrip("/")
    if "/audio/transcriptions" in url:
        return url
    if url.endswith("/v1"):
        return f"{url}/audio/transcriptions"
    return f"{url}/v1/audio/transcriptions"


def _bearer_headers(api_key: str, extra_config: dict[str, Any]) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    configured = extra_config.get("headers")
    if isinstance(configured, dict):
        headers.update({str(key): str(value) for key, value in configured.items()})
    return headers


def _transcription_fields(
    model_name: str,
    extra_config: dict[str, Any],
    *,
    language: str | None = None,
) -> dict[str, str | list[str]]:
    fields = {"model": model_name}
    resolved_language = openai_language_code(resolve_asr_language(language, extra_config))
    if resolved_language:
        fields["language"] = resolved_language
    for key in ("prompt", "temperature"):
        value = extra_config.get(key)
        if value is not None and str(value).strip():
            fields[key] = str(value)
    return fields


def _text_payload(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except (AttributeError, ValueError):
        content = getattr(response, "text", "") or getattr(response, "content", b"")
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        return {"text": str(content).strip()}
    return as_mapping(payload)


class OpenAIWhisperASRProvider(ASRProvider):
    """Native OpenAI Whisper-style transcription with word timestamps."""

    capabilities = frozenset({AudioCapability.TRANSCRIBE, AudioCapability.WORD_TIMESTAMPS})

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

    def transcribe(
        self,
        audio_path: str,
        *,
        word_timestamps: bool = False,
        language: str | None = None,
    ) -> ASRResult:
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="OpenAI Whisper ASR",
        )
        if word_timestamps:
            self.require(AudioCapability.WORD_TIMESTAMPS)
        path = Path(audio_path)
        fields = _transcription_fields(self.model_name, self.extra_config, language=language)
        # Verbose JSON is required by OpenAI when asking for timing metadata.
        fields["response_format"] = "verbose_json"
        if word_timestamps:
            # Material processing needs both lexical boundaries (for clip
            # trimming) and segment boundaries (for sentence timing).  OpenAI
            # treats this field as an array of the granularities to populate;
            # requesting only ``word`` allows a valid verbose response with no
            # ``segments`` collection at all.  httpx expands list values into
            # repeated multipart fields with the same name.
            fields["timestamp_granularities[]"] = ["word", "segment"]
        elif self.extra_config.get("segment_timestamps", True):
            fields["timestamp_granularities[]"] = "segment"
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as audio_file:
            response = provider_http.post(
                _native_transcriptions_endpoint(self.base_url, self.extra_config),
                data=fields,
                files={"file": (path.name, audio_file, media_type)},
                headers=_bearer_headers(self.api_key, self.extra_config),
                timeout=float(self.extra_config.get("timeout", 120)),
            )
        response.raise_for_status()
        payload = _text_payload(response)
        text, segments = openai_verbose_result(payload, include_words=word_timestamps)
        return ASRResult(
            text=text,
            segments=segments,
            provider_metadata={"adapter": "openai_whisper_asr", "model": self.model_name},
        )

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="OpenAI Whisper ASR",
        )


class OpenAITranscribeASRProvider(ASRProvider):
    """Native GPT/OpenAI transcription adapter that conservatively returns text only."""

    capabilities = frozenset({AudioCapability.TRANSCRIBE})

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

    def transcribe(
        self,
        audio_path: str,
        *,
        word_timestamps: bool = False,
        language: str | None = None,
    ) -> ASRResult:
        if word_timestamps:
            self.require(AudioCapability.WORD_TIMESTAMPS)
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="OpenAI transcription ASR",
        )
        path = Path(audio_path)
        fields = _transcription_fields(self.model_name, self.extra_config, language=language)
        fields["response_format"] = str(self.extra_config.get("response_format", "json"))
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as audio_file:
            response = provider_http.post(
                _native_transcriptions_endpoint(self.base_url, self.extra_config),
                data=fields,
                files={"file": (path.name, audio_file, media_type)},
                headers=_bearer_headers(self.api_key, self.extra_config),
                timeout=float(self.extra_config.get("timeout", 120)),
            )
        response.raise_for_status()
        payload = _text_payload(response)
        text = str(payload.get("text", "")).strip()
        return ASRResult(
            text=text,
            segments=[ASRSegment(text=text)] if text else [],
            provider_metadata={"adapter": "openai_transcribe_asr", "model": self.model_name},
        )

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="OpenAI transcription ASR",
        )


class OpenAICompatibleRemoteASRProvider(ASRProvider):
    """Generic text-only adapter for a user-provided OpenAI-compatible endpoint.

    ``base_url`` is deliberately treated as the complete endpoint.  Compatible
    gateways vary in path layout and are not guaranteed to implement Whisper's
    verbose/timestamp response shape.
    """

    capabilities = frozenset({AudioCapability.TRANSCRIBE})

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

    def transcribe(
        self,
        audio_path: str,
        *,
        word_timestamps: bool = False,
        language: str | None = None,
    ) -> ASRResult:
        if word_timestamps:
            self.require(AudioCapability.WORD_TIMESTAMPS)
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="OpenAI-compatible ASR",
        )
        path = Path(audio_path)
        fields = _transcription_fields(self.model_name, self.extra_config, language=language)
        response_format = self.extra_config.get("response_format")
        if response_format:
            fields["response_format"] = str(response_format)
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as audio_file:
            response = provider_http.post(
                self.base_url,
                data=fields,
                files={"file": (path.name, audio_file, media_type)},
                headers=_bearer_headers(self.api_key, self.extra_config),
                timeout=float(self.extra_config.get("timeout", 120)),
            )
        response.raise_for_status()
        payload = _text_payload(response)
        text = str(payload.get("text", "")).strip()
        # A few gateways place text in a chat-completions-like response.
        if not text:
            choices = payload.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                message = choices[0].get("message")
                if isinstance(message, dict):
                    text = str(message.get("content", "")).strip()
        return ASRResult(
            text=text,
            segments=[ASRSegment(text=text)] if text else [],
            provider_metadata={"adapter": "openai_compatible_asr", "model": self.model_name},
        )

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="OpenAI-compatible ASR",
        )
