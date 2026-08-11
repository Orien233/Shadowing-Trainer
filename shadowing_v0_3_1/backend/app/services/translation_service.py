"""Translation flow routed through the configured LLM provider contract."""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Iterable, List

import httpx
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.services.ai.audio_types import ProviderCapability
from app.services.provider_factory import get_llm_provider_with_legacy_fallback, require_provider_capabilities


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


def _build_translation_prompt(text: str) -> str:
    return (
        "Translate the following text into Simplified Chinese and return JSON only.\n"
        f"source_text: {text}"
    )


def _is_retryable_error(error: Exception) -> bool:
    if isinstance(error, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in RETRYABLE_STATUS_CODES
    return False


def _calculate_dynamic_concurrency(sentence_count: int) -> int:
    if sentence_count <= 1:
        return 1
    dynamic = max(2, math.ceil(sentence_count * 0.85))
    return max(1, min(settings.translation_concurrency, dynamic))


def _calculate_warmup_count(sentence_count: int) -> int:
    if sentence_count <= 0:
        return 0
    if sentence_count <= 6:
        return 1
    if sentence_count <= 20:
        return 2
    return 3


async def close_translation_http_client() -> None:
    """Compatibility hook retained for the FastAPI lifespan callback.

    Translation now uses the configured provider adapters directly; the old
    DeepSeek-only async HTTP client has been removed.
    """
    return None


async def translate_sentence(text: str, *, provider: Any | None = None) -> str:
    """Translate one sentence, resolving a provider only when needed."""
    source_text = text.strip()
    if not source_text:
        return ""

    max_attempts = settings.translation_max_retries + 1
    async with _translation_semaphore:
        for attempt in range(max_attempts):
            try:
                active_provider = provider
                if active_provider is None:
                    with Session(engine) as session:
                        require_provider_capabilities(session, "llm", {ProviderCapability.GENERATE_TEXT, ProviderCapability.GENERATE_JSON})
                        active_provider = get_llm_provider_with_legacy_fallback(session)
                parsed = await asyncio.to_thread(
                    active_provider.generate_json,
                    system_prompt=TRANSLATION_SYSTEM_PROMPT,
                    user_prompt=_build_translation_prompt(source_text),
                    temperature=0.2,
                )
                translation = parsed.get("translation")
                if not isinstance(translation, str) or not translation.strip():
                    raise ValueError("LLM JSON response missing 'translation'.")
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


async def _translate_with_fallback(source_text: str, provider: Any) -> str:
    try:
        return await translate_sentence(source_text, provider=provider)
    except Exception as error:
        logger.warning(
            "Translation failed for source text prefix '%s': %s",
            source_text[:60],
            error,
        )
        return f"[Translation failed] {source_text}"


async def translate_sentences(texts: Iterable[str]) -> List[str]:
    """Translate a material batch through one stable configured provider."""
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
    with Session(engine) as session:
        require_provider_capabilities(session, "llm", {ProviderCapability.GENERATE_TEXT, ProviderCapability.GENERATE_JSON})
        provider = get_llm_provider_with_legacy_fallback(session)

    results: list[str] = [""] * sentence_count
    for index in range(warmup_count):
        results[index] = await _translate_with_fallback(text_list[index], provider)

    remaining_indices = list(range(warmup_count, sentence_count))
    if not remaining_indices:
        return results

    batch_concurrency = max(1, min(target_concurrency, len(remaining_indices)))
    batch_semaphore = asyncio.Semaphore(batch_concurrency)

    async def _translate_remaining(index: int) -> None:
        async with batch_semaphore:
            results[index] = await _translate_with_fallback(text_list[index], provider)

    await asyncio.gather(*(_translate_remaining(index) for index in remaining_indices))
    return results
