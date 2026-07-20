"""Deepgram prerecorded-audio adapter."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from app.services.ai.http_transport import provider_http
from app.services.ai.asr.base import ASRProvider
from app.services.ai.audio_types import ASRResult, ASRSegment, ASRWord, AudioCapability
from app.services.ai.audio_utils import as_list, as_mapping, configuration_message, number, require_configured


def _listen_endpoint(base_url: str, extra_config: dict[str, Any]) -> str:
    explicit = extra_config.get("endpoint")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.rstrip("/")
    url = base_url.rstrip("/")
    if url.endswith("/listen"):
        return url
    if url.endswith("/v1"):
        return f"{url}/listen"
    return f"{url}/v1/listen"


class DeepgramASRProvider(ASRProvider):
    """Deepgram pre-recorded transcription with utterance/word timestamps."""

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

    def _headers(self, media_type: str) -> dict[str, str]:
        headers = {"Authorization": f"Token {self.api_key}", "Content-Type": media_type}
        configured = self.extra_config.get("headers")
        if isinstance(configured, dict):
            headers.update({str(key): str(value) for key, value in configured.items()})
        return headers

    def _params(self, *, word_timestamps: bool) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model_name,
            "smart_format": self.extra_config.get("smart_format", True),
            "punctuate": self.extra_config.get("punctuate", True),
            "utterances": self.extra_config.get("utterances", True),
        }
        if word_timestamps and self.extra_config.get("diarize") is not None:
            params["diarize"] = self.extra_config["diarize"]
        configured = self.extra_config.get("parameters")
        if isinstance(configured, dict):
            params.update(configured)
        return params

    def transcribe(self, audio_path: str, *, word_timestamps: bool = False) -> ASRResult:
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="Deepgram ASR",
        )
        if word_timestamps:
            self.require(AudioCapability.WORD_TIMESTAMPS)
        path = Path(audio_path)
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        response = provider_http.post(
            _listen_endpoint(self.base_url, self.extra_config),
            params=self._params(word_timestamps=word_timestamps),
            content=path.read_bytes(),
            headers=self._headers(media_type),
            timeout=float(self.extra_config.get("timeout", 120)),
        )
        response.raise_for_status()
        payload = as_mapping(response.json())
        text, segments = self._parse(payload, include_words=word_timestamps)
        return ASRResult(
            text=text,
            segments=segments,
            provider_metadata={"adapter": "deepgram_asr", "model": self.model_name, "metadata": payload.get("metadata", {})},
        )

    @staticmethod
    def _parse(payload: dict[str, Any], *, include_words: bool) -> tuple[str, list[ASRSegment]]:
        results = as_mapping(payload.get("results"))
        utterances = as_list(results.get("utterances") or payload.get("utterances"))
        segments: list[ASRSegment] = []
        if utterances:
            for raw_utterance in utterances:
                utterance = as_mapping(raw_utterance)
                text = str(utterance.get("transcript") or utterance.get("text") or "").strip()
                start = number(utterance.get("start"))
                end = number(utterance.get("end"), start)
                words = DeepgramASRProvider._words(utterance.get("words")) if include_words else []
                if words and end == start:
                    end = max((word.end or start) for word in words)
                if text or words:
                    segments.append(ASRSegment(text=text, start=start, end=end, words=words))
            return " ".join(segment.text for segment in segments).strip(), segments

        channel_texts: list[str] = []
        for raw_channel in as_list(results.get("channels")):
            channel = as_mapping(raw_channel)
            alternatives = as_list(channel.get("alternatives"))
            if not alternatives:
                continue
            alternative = as_mapping(alternatives[0])
            text = str(alternative.get("transcript") or "").strip()
            words = DeepgramASRProvider._words(alternative.get("words")) if include_words else []
            start = min((word.start for word in words if word.start is not None), default=0.0)
            end = max((word.end for word in words if word.end is not None), default=start)
            if text or words:
                segments.append(ASRSegment(text=text, start=start, end=end, words=words))
            if text:
                channel_texts.append(text)
        return " ".join(channel_texts).strip(), segments

    @staticmethod
    def _words(value: Any) -> list[ASRWord]:
        words: list[ASRWord] = []
        for raw_word in as_list(value):
            word = as_mapping(raw_word)
            text = str(word.get("punctuated_word") or word.get("word") or word.get("text") or "").strip()
            if not text:
                continue
            words.append(ASRWord(text=text, start=number(word.get("start")), end=number(word.get("end"))))
        return words

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="Deepgram ASR",
        )
