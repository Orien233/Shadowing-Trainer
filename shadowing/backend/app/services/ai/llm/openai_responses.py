"""OpenAI Responses API adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.ai.http_transport import provider_http
from app.services.ai.llm._shared import (
    endpoint_url,
    extract_json_object,
    json_system_prompt,
    require_api_key,
    require_nonempty_text,
    test_models_endpoint,
)
from app.services.ai.llm.base import LLMProvider


class OpenAIResponsesLLMProvider(LLMProvider):
    """Native adapter for OpenAI's ``POST /v1/responses`` contract."""

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
    def _auth_scheme(self) -> str:
        return str(self.extra_config.get("auth_scheme", "bearer")).strip().lower()

    def _headers(self) -> dict[str, str]:
        if self._auth_scheme == "none":
            return {"Content-Type": "application/json"}
        if self._auth_scheme in {"api-key", "api_key"}:
            return {"api-key": self.api_key, "Content-Type": "application/json"}
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _require_credential(self) -> None:
        if self._auth_scheme != "none":
            require_api_key(self.api_key)

    @staticmethod
    def _response_text(data: Any) -> str:
        if not isinstance(data, Mapping):
            raise ValueError("Provider response was not a JSON object.")

        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        values: list[str] = []
        refused = False
        output = data.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, Mapping):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, Mapping):
                        continue
                    if block.get("type") == "refusal":
                        refused = True
                        continue
                    text = block.get("text")
                    if block.get("type") == "output_text" and isinstance(text, str):
                        values.append(text)

        combined = "".join(values).strip()
        if combined:
            return combined
        if refused:
            raise ValueError("Provider refused to produce a response.")
        raise ValueError("Provider response did not contain output text.")

    def _complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        json_mode: bool,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        self._require_credential()
        mode = str(self.extra_config.get("json_mode", "json_schema")).lower()
        if json_mode and mode == "prompt_only":
            system_prompt = json_system_prompt(system_prompt, json_schema)

        payload: dict[str, Any] = {
            "model": self.model_name,
            "instructions": system_prompt,
            "input": user_prompt,
            "temperature": temperature,
            "store": False,
        }
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
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return require_nonempty_text(self._response_text(response.json()))

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
    ) -> str:
        return self._complete(system_prompt, user_prompt, temperature, False)

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return extract_json_object(
            self._complete(system_prompt, user_prompt, temperature, True, json_schema)
        )

    def test_connection(self) -> str:
        self._require_credential()
        return test_models_endpoint(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=min(self.timeout, 20),
            success_message="OpenAI Responses connection succeeded (metadata endpoint).",
        )


__all__ = ["OpenAIResponsesLLMProvider"]
