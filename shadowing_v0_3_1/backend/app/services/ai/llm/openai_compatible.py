import json
import re
from typing import Any

import httpx

from app.services.ai.llm.base import LLMProvider


def extract_json_object(raw_text: str) -> dict[str, Any]:
    content = raw_text.strip()
    content = re.sub(r"^```(?:json)?\\s*|\\s*```$", "", content, flags=re.IGNORECASE).strip()
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Provider returned invalid JSON.")
        value = json.loads(content[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Provider JSON response must be an object.")
    return value


class OpenAICompatibleLLMProvider(LLMProvider):
    def __init__(self, *, base_url: str, api_key: str, model_name: str, timeout: float = 60) -> None:
        self.base_url, self.api_key, self.model_name, self.timeout = base_url.rstrip("/"), api_key, model_name, timeout

    def _complete(self, system_prompt: str, user_prompt: str, temperature: float, json_mode: bool) -> str:
        if not self.api_key:
            raise ValueError("Provider API key is not configured.")
        payload: dict[str, Any] = {"model": self.model_name, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "temperature": temperature}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        response = httpx.post(f"{self.base_url}/chat/completions", json=payload, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Provider response did not contain a chat completion.") from exc
        if isinstance(content, list):
            content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Provider returned an empty response.")
        return content.strip()

    def generate_text(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
        return self._complete(system_prompt, user_prompt, temperature, False)

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict[str, Any]:
        return extract_json_object(self._complete(system_prompt, user_prompt, temperature, True))

    def test_connection(self) -> str:
        self.generate_text(system_prompt="Reply with OK.", user_prompt="Connection test.", temperature=0)
        return "LLM connection succeeded."
