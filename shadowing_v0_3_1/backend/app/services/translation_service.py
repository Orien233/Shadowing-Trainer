from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from typing import Any, Iterable, List

import httpx

from app.core.config import settings
from app.core.database import engine
from app.services.provider_factory import get_llm_provider_with_legacy_fallback
from sqlmodel import Session


logger = logging.getLogger(__name__)

TRANSLATION_SYSTEM_PROMPT = """You are a translation assistant for language practice.
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

RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_translation_semaphore = asyncio.Semaphore(settings.translation_concurrency)
_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(settings.translation_request_timeout_seconds),
    limits=httpx.Limits(
        max_connections=settings.translation_max_connections,
        max_keepalive_connections=settings.translation_max_keepalive_connections,
    ),
)


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


def _is_retryable_error(error: Exception) -> bool:
    if isinstance(error, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in RETRYABLE_STATUS_CODES
    return False


def _calculate_dynamic_concurrency(sentence_count: int) -> int:
    if sentence_count <= 1:
        return 1

    max_limit = settings.translation_concurrency
    # Aggressive default: use about 85% of sentence count, then cap at ENV max.
    dynamic = max(2, math.ceil(sentence_count * 0.85))
    return max(1, min(max_limit, dynamic))


def _calculate_warmup_count(sentence_count: int) -> int:
    if sentence_count <= 0:
        return 0
    if sentence_count <= 6:
        return 1
    if sentence_count <= 20:
        return 2
    return 3


async def _translate_with_fallback(source_text: str) -> str:
    try:
        return await translate_sentence(source_text)
    except Exception as error:
        logger.warning(
            "Translation failed for source text prefix '%s': %s",
            source_text[:60],
            error,
        )
        return f"[Translation failed] {source_text}"


async def close_translation_http_client() -> None:
    if not _http_client.is_closed:
        await _http_client.aclose()


async def _request_translation(source_text: str) -> dict[str, Any]:
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

    response = await _http_client.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data: Any = response.json()
    if not isinstance(data, dict):
        raise ValueError("DeepSeek response is not a JSON object.")
    return data


# translate a single sentence using the DeepSeek API, returning the translated text
async def translate_sentence(text: str) -> str:
    source_text = text.strip()
    if not source_text:
        return ""

    max_attempts = settings.translation_max_retries + 1
    async with _translation_semaphore:
        for attempt in range(max_attempts):
            try:
                with Session(engine) as session:
                    provider = get_llm_provider_with_legacy_fallback(session)
                parsed = await asyncio.to_thread(
                    provider.generate_json,
                    system_prompt=TRANSLATION_SYSTEM_PROMPT,
                    user_prompt=_build_translation_prompt(source_text),
                    temperature=0.2,
                )
                translation = parsed.get("translation")
                if not isinstance(translation, str) or not translation.strip():
                    raise ValueError("DeepSeek JSON response missing 'translation'.")
                return translation.strip()
            except Exception as error:
                if attempt >= max_attempts - 1 or not _is_retryable_error(error):
                    raise
                delay = settings.translation_retry_base_seconds * (2**attempt)
                logger.warning(
                    "Retrying translation after %s (attempt %s/%s, delay %.2fs).",
                    type(error).__name__,
                    attempt + 1,
                    max_attempts,
                    delay,
                )
                await asyncio.sleep(delay)

    raise RuntimeError("Unexpected translation retry flow.")


# translate a list of sentences concurrently, returning a list of translated texts in the same order
async def translate_sentences(texts: Iterable[str]) -> List[str]:
    text_list = list(texts)
    if not text_list:
        return []

    sentence_count = len(text_list)
    target_concurrency = _calculate_dynamic_concurrency(sentence_count)
    warmup_count = min(_calculate_warmup_count(sentence_count), sentence_count)
    logger.info(
        "Translation scheduling: total=%s warmup=%s dynamic_concurrency=%s max_limit=%s",
        sentence_count,
        warmup_count,
        target_concurrency,
        settings.translation_concurrency,
    )

    results: list[str] = [""] * sentence_count

    # Warm up provider-side prompt cache and connection path with a minimal sequential phase.
    for index in range(warmup_count):
        results[index] = await _translate_with_fallback(text_list[index])

    remaining_indices = list(range(warmup_count, sentence_count))
    if not remaining_indices:
        return results

    batch_concurrency = max(1, min(target_concurrency, len(remaining_indices)))
    batch_semaphore = asyncio.Semaphore(batch_concurrency)

    async def _translate_remaining(index: int) -> None:
        async with batch_semaphore:
            results[index] = await _translate_with_fallback(text_list[index])

    await asyncio.gather(*(_translate_remaining(index) for index in remaining_indices))
    return results
