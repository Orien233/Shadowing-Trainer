"""OpenAI Chat Completions protocol adapter."""

from typing import Any

from app.services.ai.http_transport import provider_http
from app.services.ai.llm.base import LLMProvider
from app.services.ai.llm._shared import (
    extract_json_object,
    json_system_prompt,
    require_api_key,
    require_nonempty_text,
)


class OpenAIChatCompatibleLLMProvider(LLMProvider):
    """Chat Completions adapter for OpenAI and protocol-compatible endpoints."""

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

    def _complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        json_mode: bool,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        self._require_credential()
        mode = str(self.extra_config.get("json_mode", "response_format")).lower()
        if json_mode and mode == "prompt_only":
            system_prompt = json_system_prompt(system_prompt, json_schema)
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if json_mode and mode != "prompt_only":
            if mode == "json_schema" and json_schema:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": str(self.extra_config.get("json_schema_name", "response")),
                        "schema": json_schema,
                        "strict": True,
                    },
                }
            else:
                payload["response_format"] = {"type": "json_object"}
        response = provider_http.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Provider response did not contain a chat completion.") from exc
        if isinstance(content, list):
            content = "".join(
                str(item.get("text", "")) for item in content if isinstance(item, dict)
            )
        if not isinstance(content, str):
            raise ValueError("Provider returned an empty response.")
        return require_nonempty_text(content)

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
        response = provider_http.get(
            f"{self.base_url}/models",
            headers=self._headers(),
            timeout=min(self.timeout, 20),
        )
        response.raise_for_status()
        return "LLM connection succeeded (metadata endpoint)."


__all__ = ["OpenAIChatCompatibleLLMProvider"]
