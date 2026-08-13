"""Adapter for Anthropic's native Messages API."""

from __future__ import annotations

from typing import Any, Mapping

from app.services.ai.http_transport import provider_http
from app.services.ai.llm._shared import (
    endpoint_url,
    extract_json_object,
    json_system_prompt,
    positive_int,
    require_api_key,
    require_nonempty_text,
    text_from_blocks,
)
from app.services.ai.llm.base import LLMProvider


class AnthropicMessagesLLMProvider(LLMProvider):
    """Anthropic Messages API adapter behind the common LLM provider contract."""

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
        return {
            "x-api-key": self.api_key,
            "anthropic-version": str(self.extra_config.get("api_version", "2023-06-01")),
            "content-type": "application/json",
        }

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
        if json_mode:
            # The common contract needs structured objects on every model.  A
            # prompt-enforced object is portable; users may opt into newer
            # Anthropic structured-output features later without paid fallback.
            system_prompt = json_system_prompt(system_prompt, json_schema)
        payload: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": positive_int(self.extra_config.get("max_tokens"), 1024),
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        response = provider_http.post(
            endpoint_url(self.base_url, "messages"),
            json=payload,
            headers=self._headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return self._extract_response_text(response.json())

    @staticmethod
    def _extract_response_text(payload: Any) -> str:
        if not isinstance(payload, Mapping):
            raise ValueError("Provider returned an invalid Anthropic Messages payload.")
        text = text_from_blocks(payload.get("content"), text_keys=("text",))
        return require_nonempty_text(text, "Provider response did not contain a text block.")

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
            endpoint_url(self.base_url, "models"),
            headers=self._headers,
            timeout=min(self.timeout, 20),
        )
        response.raise_for_status()
        return "LLM connection succeeded (metadata endpoint)."


__all__ = ["AnthropicMessagesLLMProvider"]
