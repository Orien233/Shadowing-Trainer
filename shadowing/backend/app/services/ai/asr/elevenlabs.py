"""ElevenLabs Scribe speech-to-text adapter."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from app.services.ai.http_transport import provider_http
from app.services.ai.asr._helpers import elevenlabs_result
from app.services.ai.asr.base import ASRProvider
from app.services.ai.audio_types import ASRResult, AudioCapability
from app.services.ai.audio_utils import as_mapping, configuration_message, require_configured


def _speech_to_text_endpoint(base_url: str, extra_config: dict[str, Any]) -> str:
    explicit = extra_config.get("endpoint")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.rstrip("/")
    url = base_url.rstrip("/")
    if url.endswith("/speech-to-text"):
        return url
    if url.endswith("/v1"):
        return f"{url}/speech-to-text"
    return f"{url}/v1/speech-to-text"


class ElevenLabsASRProvider(ASRProvider):
    """ElevenLabs Scribe adapter, including optional word-level timestamps."""

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

    def _headers(self) -> dict[str, str]:
        headers = {"xi-api-key": self.api_key}
        configured = self.extra_config.get("headers")
        if isinstance(configured, dict):
            headers.update({str(key): str(value) for key, value in configured.items()})
        return headers

    def _fields(self, *, word_timestamps: bool) -> dict[str, str]:
        fields = {"model_id": self.model_name}
        for key in (
            "language_code",
            "tag_audio_events",
            "num_speakers",
            "diarize",
            "diarization_threshold",
            "file_format",
            "use_multi_channel",
            "multichannel_output_style",
            "keyterms",
        ):
            value = self.extra_config.get(key)
            if value is not None:
                fields[key] = str(value).lower() if isinstance(value, bool) else str(value)
        if self.extra_config.get("language") and "language_code" not in fields:
            fields["language_code"] = str(self.extra_config["language"])
        fields["timestamps_granularity"] = "word" if word_timestamps else str(
            self.extra_config.get("timestamps_granularity", "none")
        )
        return fields

    def transcribe(self, audio_path: str, *, word_timestamps: bool = False) -> ASRResult:
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="ElevenLabs ASR",
        )
        if word_timestamps:
            self.require(AudioCapability.WORD_TIMESTAMPS)
        path = Path(audio_path)
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as audio_file:
            response = provider_http.post(
                _speech_to_text_endpoint(self.base_url, self.extra_config),
                data=self._fields(word_timestamps=word_timestamps),
                files={"file": (path.name, audio_file, media_type)},
                headers=self._headers(),
                timeout=float(self.extra_config.get("timeout", 120)),
            )
        response.raise_for_status()
        payload = as_mapping(response.json())
        text, segments = elevenlabs_result(payload, include_words=word_timestamps)
        return ASRResult(
            text=text,
            segments=segments,
            provider_metadata={
                "adapter": "elevenlabs_asr",
                "model": self.model_name,
                "language_code": payload.get("language_code"),
            },
        )

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="ElevenLabs ASR",
        )
