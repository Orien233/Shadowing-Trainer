"""DashScope synchronous-response file-transcription adapter.

The current application intentionally supports only synchronous file ASR.  A
DashScope deployment that responds with an asynchronous task id is rejected
with a clear message instead of quietly introducing polling, batch handling,
or restart recovery outside the existing job contract.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from app.services.ai.http_transport import provider_http
from app.services.ai.asr.base import ASRProvider
from app.services.ai.audio_types import ASRResult, ASRSegment, AudioCapability
from app.services.ai.audio_utils import as_list, as_mapping, configuration_message, number, require_configured


def _transcription_endpoint(base_url: str, extra_config: dict[str, Any]) -> str:
    explicit = extra_config.get("endpoint")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.rstrip("/")
    url = base_url.rstrip("/")
    if url.endswith("/transcription"):
        return url
    if url.endswith("/v1"):
        return f"{url}/services/audio/asr/transcription"
    return f"{url}/api/v1/services/audio/asr/transcription"


class DashScopeASRProvider(ASRProvider):
    """DashScope immediate-result ASR adapter (text-only capability)."""

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

    def _headers(self, *, asynchronous: bool = True) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if asynchronous:
            headers["X-DashScope-Async"] = "enable"
        configured = self.extra_config.get("headers")
        if isinstance(configured, dict):
            headers.update({str(key): str(value) for key, value in configured.items()})
        return headers

    def _audio_reference(self, audio_path: str) -> str:
        configured = self.extra_config.get("file_url") or self.extra_config.get("audio_url")
        if isinstance(configured, str) and configured.strip():
            return configured.format(audio_path=audio_path)
        if audio_path.startswith(("https://", "http://")):
            return audio_path
        path = Path(audio_path)
        media_type = mimetypes.guess_type(path.name)[0] or "audio/wav"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{media_type};base64,{encoded}"

    def _payload(self, audio_path: str) -> dict[str, Any]:
        reference = self._audio_reference(audio_path)
        input_key = str(self.extra_config.get("input_key", "file_url"))
        input_value: Any = [reference] if input_key == "file_urls" else reference
        parameters = self.extra_config.get("parameters")
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": {input_key: input_value},
            "parameters": dict(parameters) if isinstance(parameters, dict) else {},
        }
        if self.extra_config.get("language"):
            payload["parameters"].setdefault("language_hints", [str(self.extra_config["language"])])
        return payload

    def transcribe(self, audio_path: str, *, word_timestamps: bool = False) -> ASRResult:
        if word_timestamps:
            self.require(AudioCapability.WORD_TIMESTAMPS)
        require_configured(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="DashScope ASR",
        )
        endpoint = _transcription_endpoint(self.base_url, self.extra_config)
        response = provider_http.post(
            endpoint,
            json=self._payload(audio_path),
            headers=self._headers(),
            timeout=float(self.extra_config.get("timeout", 120)),
        )
        response.raise_for_status()
        payload = as_mapping(response.json())
        output = as_mapping(payload.get("output"))
        if output.get("task_id") or payload.get("task_id"):
            raise ValueError(
                "This DashScope endpoint returned an asynchronous task. "
                "The current ASR adapter supports synchronous file responses only."
            )
        text, segments = self._parse(payload)
        return ASRResult(
            text=text,
            segments=segments,
            provider_metadata={"adapter": "dashscope_asr", "model": self.model_name},
        )

    @staticmethod
    def _parse(payload: dict[str, Any]) -> tuple[str, list[ASRSegment]]:
        candidates: list[dict[str, Any]] = [payload, as_mapping(payload.get("output"))]
        transcripts = as_list(payload.get("transcripts"))
        for item in transcripts:
            candidates.append(as_mapping(item))
        segments: list[ASRSegment] = []
        text_parts: list[str] = []
        for candidate in candidates:
            text = str(candidate.get("text") or candidate.get("transcript") or "").strip()
            if text and text not in text_parts:
                text_parts.append(text)
            for raw_sentence in as_list(candidate.get("sentences")):
                sentence = as_mapping(raw_sentence)
                sentence_text = str(sentence.get("text") or sentence.get("transcript") or "").strip()
                start = number(sentence.get("begin_time") or sentence.get("start_time") or sentence.get("start"))
                end = number(sentence.get("end_time") or sentence.get("end"), start)
                if max(start, end) > 10_000:  # DashScope file results often use milliseconds.
                    start, end = start / 1000, end / 1000
                if sentence_text:
                    segments.append(ASRSegment(text=sentence_text, start=start, end=end))
        text = " ".join(text_parts).strip() or " ".join(segment.text for segment in segments).strip()
        if not segments and text:
            segments = [ASRSegment(text=text)]
        return text, segments

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="DashScope ASR",
        )
