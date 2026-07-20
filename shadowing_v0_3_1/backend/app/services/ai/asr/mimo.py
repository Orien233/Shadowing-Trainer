from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from app.services.ai.http_transport import provider_http
from app.services.ai.asr.base import ASRProvider
from app.services.ai.audio_types import ASRResult, ASRSegment, AudioCapability
from app.services.ai.audio_utils import configuration_message


class MiMoASRProvider(ASRProvider):
    """Adapter for MiMo V2.5 ASR Chat Completions API.

    The API accepts a Base64 data URI in an ``input_audio`` content part and
    returns transcription text in the chat completion message.
    """

    capabilities = frozenset({AudioCapability.TRANSCRIBE})

    def __init__(self, base_url: str, api_key: str, model_name: str, extra_config: dict[str, Any] | None = None) -> None:
        self.base_url, self.api_key, self.model_name = base_url.rstrip("/"), api_key, model_name
        self.extra_config = extra_config or {}

    def _headers(self) -> dict[str, str]:
        if self.extra_config.get("auth_scheme") == "api-key":
            return {"api-key": self.api_key, "Content-Type": "application/json"}
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def transcribe(self, audio_path: str, *, word_timestamps: bool = False) -> ASRResult:
        if not self.api_key:
            raise ValueError("Provider API key is not configured.")
        if word_timestamps:
            self.require(AudioCapability.WORD_TIMESTAMPS)
        path = Path(audio_path)
        mime_type = mimetypes.guess_type(path.name)[0] or "audio/wav"
        encoded_audio = base64.b64encode(path.read_bytes()).decode("ascii")
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": f"data:{mime_type};base64,{encoded_audio}"}}]}],
            "asr_options": {"language": self.extra_config.get("language", "auto")},
        }
        response = provider_http.post(self.base_url, json=payload, headers=self._headers(), timeout=120)
        response.raise_for_status()
        data = response.json()
        try:
            text = str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("MiMo ASR response did not contain transcription text.") from exc
        return ASRResult(text=text, segments=[ASRSegment(text=text)] if text else [], provider_metadata={"adapter": "mimo_asr", "model": self.model_name})

    def test_connection(self) -> str:
        return configuration_message(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            provider_name="MiMo ASR",
        )
