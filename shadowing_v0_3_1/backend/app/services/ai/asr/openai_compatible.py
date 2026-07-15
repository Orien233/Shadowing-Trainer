from pathlib import Path
from typing import Any

import httpx

from app.services.ai.asr.base import ASRProvider


class OpenAICompatibleRemoteASRProvider(ASRProvider):
    def __init__(self, *, base_url: str, api_key: str, model_name: str, extra_config: dict[str, Any] | None = None) -> None:
        self.base_url, self.api_key, self.model_name = base_url.rstrip("/"), api_key, model_name
        self.extra_config = extra_config or {}

    def transcribe(self, audio_path: str, *, word_timestamps: bool = False) -> list[dict[str, Any]]:
        if not self.api_key:
            raise ValueError("Provider API key is not configured.")
        path = Path(audio_path)
        data: dict[str, str] = {"model": self.model_name, "response_format": "verbose_json"}
        if word_timestamps:
            data["timestamp_granularities[]"] = "word"
        with path.open("rb") as audio_file:
            response = httpx.post(f"{self.base_url}/audio/transcriptions", data=data, files={"file": (path.name, audio_file, "application/octet-stream")}, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=120)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("ASR provider returned an invalid response.")
        segments = payload.get("segments")
        if isinstance(segments, list):
            words = payload.get("words") if isinstance(payload.get("words"), list) else []
            return [{"start": float(item.get("start", 0)), "end": float(item.get("end", 0)), "text": str(item.get("text", "")).strip(), "words": [{"start": word.get("start"), "end": word.get("end"), "word": word.get("word", "")} for word in words if isinstance(word, dict) and float(word.get("start", 0)) >= float(item.get("start", 0)) and float(word.get("end", 0)) <= float(item.get("end", 0))]} for item in segments if isinstance(item, dict)]
        text = str(payload.get("text", "")).strip()
        return [{"start": 0.0, "end": 0.0, "text": text, "words": []}] if text else []

    def test_connection(self) -> str:
        if not self.api_key:
            raise ValueError("Provider API key is not configured.")
        response = httpx.get(
            f"{self.base_url}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=20,
        )
        response.raise_for_status()
        return "Remote ASR connection succeeded."
