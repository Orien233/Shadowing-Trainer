from __future__ import annotations

import json
import re
from typing import Any, Iterable, List

import httpx

from app.core.config import settings


TRANSLATION_SYSTEM_PROMPT = """You are a translation assistant for shadowing practice.
Translate input text into natural, concise Simplified Chinese.
You must return a valid JSON object only.
Required schema:
{
  "translation": "translated text"
}
Rules:
- No markdown code fences.
- No extra keys.
- No explanations.
"""

# build the user prompt for translation, asking for JSON output only
def _build_translation_prompt(text: str) -> str:
    return (
        "Translate the following text into Simplified Chinese and return JSON only.\n"
        f"source_text: {text}"
    )

# extract the message content from the DeepSeek response, handling both plain text and structured content blocks
def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("DeepSeek response has no choices.")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("DeepSeek response choice is invalid.")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("DeepSeek response has no message object.")

    content = message.get("content", "")
    if isinstance(content, str):
        return content

    # Some compatible APIs may return structured content blocks.
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str):
                text_parts.append(text)
        return "".join(text_parts)

    raise ValueError("DeepSeek response content is invalid.")

# extract a JSON object from the raw text, handling possible code fences or extra text
def _extract_json_object(raw_text: str) -> dict[str, Any]:
    content = raw_text.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"\s*```$", "", content)
        content = content.strip()

    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        candidate = content[start : end + 1]
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("DeepSeek response is not a valid JSON object.")

# translate a single sentence using the DeepSeek API, returning the translated text
async def translate_sentence(text: str) -> str:
    source_text = text.strip()
    if not source_text:
        return ""

    if not settings.deepseek_api_key:
        return f"[DeepSeek API key missing] {source_text}"

    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
            {"role": "user", "content": _build_translation_prompt(source_text)},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data: dict[str, Any] = response.json()

    content = _extract_message_content(data)
    parsed = _extract_json_object(content)
    translation = parsed.get("translation")
    if not isinstance(translation, str) or not translation.strip():
        raise ValueError("DeepSeek JSON response missing 'translation'.")
    return translation.strip()

# translate a list of sentences concurrently, returning a list of translated texts in the same order
async def translate_sentences(texts: Iterable[str]) -> List[str]:
    results: List[str] = []
    for text in texts:
        try:
            results.append(await translate_sentence(text))
        except Exception:
            results.append(f"[Translation failed] {text}")
    return results
