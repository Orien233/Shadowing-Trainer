"""Adapter for the Gemini ``models.generateContent`` REST protocol."""

from __future__ import annotations

from typing import Any, Mapping

from app.services.ai.http_transport import provider_http
from app.services.ai.llm._shared import (
    endpoint_url,
    extract_json_object,
    positive_int,
    quote_model_name,
    require_api_key,
    require_nonempty_text,
    text_from_blocks,
)
from app.services.ai.llm.base import LLMProvider


class GeminiGenerateContentLLMProvider(LLMProvider):
    """Gemini native REST adapter behind the project's LLM provider contract."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout: float = 60,
        extra_config: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout
        self.extra_config = extra_config or {}

    @property
    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key, "content-type": "application/json"}

    @property
    def _api_base_url(self) -> str:
        """Permit a host-only Gemini URL plus an optional public API version."""
        api_version = str(self.extra_config.get("api_version", "v1beta")).strip("/")
        if not api_version or self.base_url.rstrip("/").endswith(f"/{api_version}"):
            return self.base_url
        return endpoint_url(self.base_url, api_version)

    def _complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        *,
        json_mode: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        require_api_key(self.api_key)
        generation_config: dict[str, Any] = {"temperature": temperature}
        max_output_tokens = self.extra_config.get("max_output_tokens")
        if max_output_tokens is not None:
            generation_config["maxOutputTokens"] = positive_int(max_output_tokens, 1024)
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
            if json_schema:
                generation_config["responseSchema"] = json_schema
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": generation_config,
        }
        endpoint = endpoint_url(
            self._api_base_url,
            f"models/{quote_model_name(self.model_name)}:generateContent",
        )
        response = provider_http.post(endpoint, json=payload, headers=self._headers, timeout=self.timeout)
        response.raise_for_status()
        return self._extract_response_text(response.json())

    @staticmethod
    def _extract_response_text(payload: Any) -> str:
        if not isinstance(payload, Mapping):
            raise ValueError("Provider returned an invalid Gemini payload.")
        candidates = payload.get("candidates")
        if isinstance(candidates, list):
            for candidate in candidates:
                if not isinstance(candidate, Mapping):
                    continue
                content = candidate.get("content")
                if isinstance(content, Mapping):
                    text = text_from_blocks(content.get("parts"), text_keys=("text",))
                    if text:
                        return text
        if payload.get("promptFeedback"):
            raise ValueError("Gemini blocked the prompt before producing a response.")
        raise ValueError("Provider response did not contain candidate text.")

    def generate_text(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
        return self._complete(system_prompt, user_prompt, temperature)

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return extract_json_object(
            self._complete(
                system_prompt,
                user_prompt,
                temperature,
                json_mode=True,
                json_schema=json_schema,
            )
        )

    def test_connection(self) -> str:
        require_api_key(self.api_key)
        response = provider_http.get(
            endpoint_url(self._api_base_url, "models"),
            headers=self._headers,
            timeout=min(self.timeout, 20),
        )
        response.raise_for_status()
        return "LLM connection succeeded (metadata endpoint)."


__all__ = ["GeminiGenerateContentLLMProvider"]
