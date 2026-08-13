"""Azure Speech Fast Transcription adapter."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from app.services.ai.http_transport import provider_http
from app.services.ai.asr.base import ASRProvider
from app.services.ai.audio_types import ASRResult, ASRSegment, ASRWord, AudioCapability
from app.services.ai.audio_utils import as_list, as_mapping, configuration_message, number, require_configured


def _fast_transcription_endpoint(base_url: str, extra_config: dict[str, Any]) -> str:
    explicit = extra_config.get("endpoint")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.rstrip("/")
    url = base_url.rstrip("/")
    if "transcriptions:transcribe" in url:
        return url
    return f"{url}/speechtotext/transcriptions:transcribe"


def _azure_headers(api_key: str, extra_config: dict[str, Any]) -> dict[str, str]:
    if str(extra_config.get("auth_scheme", "")).lower() == "bearer":
        headers = {"Authorization": f"Bearer {api_key}"}
    else:
        headers = {"Ocp-Apim-Subscription-Key": api_key}
    configured = extra_config.get("headers")
    if isinstance(configured, dict):
        headers.update({str(key): str(value) for key, value in configured.items()})
    return headers


def _milliseconds(item: dict[str, Any], key: str) -> float:
    if item.get(f"{key}Milliseconds") is not None:
        return number(item[f"{key}Milliseconds"]) / 1000
    # Azure Fast Transcription's REST schema calls these integer milliseconds.
    if item.get(key) is not None:
        return number(item[key]) / 1000
    if item.get(f"{key}InTicks") is not None:
        return number(item[f"{key}InTicks"]) / 10_000_000
    return 0.0


def _definition(extra_config: dict[str, Any], model_name: str) -> dict[str, Any]:
    configured = extra_config.get("definition")
    definition = dict(configured) if isinstance(configured, dict) else {}
    locales = extra_config.get("locales")
    if isinstance(locales, list):
        definition.setdefault("locales", [str(locale) for locale in locales if str(locale).strip()])
    elif extra_config.get("language"):
        definition.setdefault("locales", [str(extra_config["language"])])
    if extra_config.get("use_model_name"):
        definition.setdefault("model", model_name)
    return definition


class AzureSpeechASRProvider(ASRProvider):
    """Synchronous Azure Fast Transcription with phrase and word timing data."""

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

    def transcribe(self, audio_path: str, *, word_timestamps: bool = False) -> ASRResult:
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="Azure Speech ASR",
        )
        if word_timestamps:
            self.require(AudioCapability.WORD_TIMESTAMPS)
        path = Path(audio_path)
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        api_version = str(self.extra_config.get("api_version", "2025-10-15"))
        with path.open("rb") as audio_file:
            response = provider_http.post(
                _fast_transcription_endpoint(self.base_url, self.extra_config),
                params={"api-version": api_version},
                data={"definition": json.dumps(_definition(self.extra_config, self.model_name))},
                files={"audio": (path.name, audio_file, media_type)},
                headers=_azure_headers(self.api_key, self.extra_config),
                timeout=float(self.extra_config.get("timeout", 120)),
            )
        response.raise_for_status()
        payload = as_mapping(response.json())
        segments = self._segments(payload, include_words=word_timestamps)
        text = self._combined_text(payload) or " ".join(segment.text for segment in segments).strip()
        return ASRResult(
            text=text,
            segments=segments,
            provider_metadata={
                "adapter": "azure_speech_asr",
                "model": self.model_name,
                "duration_seconds": number(payload.get("durationMilliseconds")) / 1000,
            },
        )

    @staticmethod
    def _combined_text(payload: dict[str, Any]) -> str:
        combined = payload.get("combinedPhrases") or payload.get("combinedRecognizedPhrases")
        if isinstance(combined, str):
            return combined.strip()
        texts = [
            str(item.get("text") or item.get("display") or "").strip()
            for item in as_list(combined)
            if isinstance(item, dict)
        ]
        if texts:
            return " ".join(text for text in texts if text).strip()
        return str(payload.get("DisplayText", "")).strip()

    @staticmethod
    def _segments(payload: dict[str, Any], *, include_words: bool) -> list[ASRSegment]:
        raw_phrases = payload.get("phrases") or payload.get("recognizedPhrases") or []
        segments: list[ASRSegment] = []
        for raw_phrase in as_list(raw_phrases):
            phrase = as_mapping(raw_phrase)
            text = str(phrase.get("text") or phrase.get("display") or "").strip()
            if not text:
                nbest = as_list(phrase.get("nBest"))
                if nbest and isinstance(nbest[0], dict):
                    text = str(nbest[0].get("display") or nbest[0].get("lexical") or "").strip()
            start = _milliseconds(phrase, "offset")
            duration = _milliseconds(phrase, "duration")
            words: list[ASRWord] = []
            if include_words:
                source_words = phrase.get("words")
                if not isinstance(source_words, list):
                    nbest = as_list(phrase.get("nBest"))
                    source_words = nbest[0].get("displayWords") if nbest and isinstance(nbest[0], dict) else []
                for raw_word in as_list(source_words):
                    word = as_mapping(raw_word)
                    word_text = str(word.get("text") or word.get("word") or "").strip()
                    if not word_text:
                        continue
                    word_start = _milliseconds(word, "offset")
                    word_duration = _milliseconds(word, "duration")
                    words.append(
                        ASRWord(text=word_text, start=word_start, end=round(word_start + word_duration, 6))
                    )
            if words and not duration:
                duration = max((word.end or start) for word in words) - start
            if text or words:
                segments.append(ASRSegment(text=text, start=start, end=round(start + duration, 6), words=words))
        return segments

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="Azure Speech ASR",
        )
