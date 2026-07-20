"""Adapter for OpenAI's Responses API request and response shape."""

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


class OpenAIResponsesLLMProvider(LLMProvider):
    """OpenAI Responses API adapter behind the project's LLM contract."""

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
        scheme = str(self.extra_config.get("auth_scheme", "bearer")).strip().lower()
        if scheme == "none":
            return {"content-type": "application/json"}
        if scheme in {"api-key", "api_key"}:
            return {"api-key": self.api_key, "content-type": "application/json"}
        return {"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"}

    def _require_credential(self) -> None:
        if str(self.extra_config.get("auth_scheme", "bearer")).strip().lower() != "none":
            require_api_key(self.api_key)

    def _complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        *,
        json_mode: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        self._require_credential()
        mode = str(self.extra_config.get("json_mode", "json_object")).lower()
        if json_mode and mode == "prompt_only":
            system_prompt = json_system_prompt(system_prompt, json_schema)
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
            ],
            "temperature": temperature,
        }
        max_output_tokens = self.extra_config.get("max_output_tokens")
        if max_output_tokens is not None:
            payload["max_output_tokens"] = positive_int(max_output_tokens, 1024)
        if json_mode and mode != "prompt_only":
            if mode == "json_schema" and json_schema:
                payload["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": str(self.extra_config.get("json_schema_name", "response")),
                        "schema": json_schema,
                        "strict": True,
                    }
                }
            else:
                payload["text"] = {"format": {"type": "json_object"}}

        response = provider_http.post(
            endpoint_url(self.base_url, "responses"),
            json=payload,
            headers=self._headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return self._extract_response_text(response.json())

    @staticmethod
    def _extract_response_text(payload: Any) -> str:
        if not isinstance(payload, Mapping):
            raise ValueError("Provider returned an invalid Responses API payload.")
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        values: list[str] = []
        output = payload.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, Mapping):
                    continue
                text = text_from_blocks(item.get("content"), text_keys=("text", "output_text"))
                if text:
                    values.append(text)
        return require_nonempty_text("".join(values), "Provider response did not contain output text.")

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
        self._require_credential()
        response = provider_http.get(
            endpoint_url(self.base_url, "models"),
            headers=self._headers,
            timeout=min(self.timeout, 20),
        )
        response.raise_for_status()
        return "LLM connection succeeded (metadata endpoint)."


__all__ = ["OpenAIResponsesLLMProvider"]
