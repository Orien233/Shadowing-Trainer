"""Small protocol-neutral helpers shared by remote LLM adapters."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping
from urllib.parse import quote

from app.services.ai.http_transport import provider_http


def extract_json_object(raw_text: str) -> dict[str, Any]:
    """Accept a JSON object with an optional markdown fence, never a JSON array."""
    content = raw_text.strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE).strip()
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


def require_api_key(api_key: str) -> None:
    if not api_key:
        raise ValueError("Provider API key is not configured.")


def endpoint_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def json_system_prompt(system_prompt: str, json_schema: dict[str, Any] | None = None) -> str:
    """Make prompt-enforced JSON mode explicit for protocols without JSON mode."""
    instruction = "Return only a valid JSON object. Do not use Markdown fences or add explanation."
    if json_schema:
        instruction = f"{instruction} The object must follow this JSON Schema: {json.dumps(json_schema, ensure_ascii=False, separators=(',', ':'))}"
    return f"{system_prompt.rstrip()}\n\n{instruction}" if system_prompt.strip() else instruction


def text_from_blocks(blocks: Any, *, text_keys: Iterable[str] = ("text",)) -> str:
    """Extract and concatenate text from common provider content block layouts."""
    if isinstance(blocks, str):
        return blocks.strip()
    if not isinstance(blocks, list):
        return ""
    values: list[str] = []
    for block in blocks:
        if isinstance(block, str):
            values.append(block)
            continue
        if not isinstance(block, Mapping):
            continue
        for key in text_keys:
            value = block.get(key)
            if isinstance(value, str):
                values.append(value)
                break
    return "".join(values).strip()


def require_nonempty_text(value: str, message: str = "Provider returned an empty response.") -> str:
    if not value or not value.strip():
        raise ValueError(message)
    return value.strip()


def test_models_endpoint(*, base_url: str, headers: Mapping[str, str], timeout: float, success_message: str) -> str:
    """Use provider metadata, not a generation request, for a no-cost test."""
    response = provider_http.get(endpoint_url(base_url, "models"), headers=dict(headers), timeout=timeout)
    response.raise_for_status()
    return success_message


def quote_model_name(model_name: str) -> str:
    return quote(model_name.removeprefix("models/").strip(), safe="-._~")
