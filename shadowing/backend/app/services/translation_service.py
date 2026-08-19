"""Translation flow routed through the configured LLM provider contract."""

from __future__ import annotations

import asyncio
import logging
import math
import threading
from typing import Any, Iterable, List

import httpx
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.services.ai.audio_types import ProviderCapability
from app.services.language_catalog import LANGUAGE_CATALOG, normalize_language_tag
from app.services.provider_factory import get_provider, require_provider_capabilities


logger = logging.getLogger(__name__)

DEFAULT_SOURCE_LANGUAGE = "en"
DEFAULT_TARGET_LANGUAGE = "zh-CN"

RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_translation_semaphore = threading.BoundedSemaphore(settings.translation_concurrency)


def _generate_json_with_slot(provider: Any, **kwargs: Any) -> dict[str, Any]:
    """Apply one process-wide limit without binding it to an event loop.

    Material translation runs on FastAPI's loop, while persisted TTS jobs run
    their translation phase in a worker thread with a separate loop. An
    ``asyncio.Semaphore`` cannot safely coordinate both. Keeping acquisition,
    the blocking provider call, and release in one executor thread makes the
    limit loop-independent and cancellation-safe.
    """
    with _translation_semaphore:
        return provider.generate_json(**kwargs)


def _describe_language(language: str) -> tuple[str, str]:
    """Return a canonical BCP-47 tag and catalog English name for a prompt."""
    canonical_tag = normalize_language_tag(language)
    descriptor = next(item for item in LANGUAGE_CATALOG if item.code == canonical_tag)
    return canonical_tag, descriptor.english_name


def _build_translation_system_prompt(source_language: str, target_language: str) -> str:
    source_tag, source_name = _describe_language(source_language)
    target_tag, target_name = _describe_language(target_language)
    return f"""You are a translation assistant for language practice.
Translate input text from {source_name} ({source_tag}) into natural, concise {target_name} ({target_tag}).
You must return a valid JSON object only.
Required schema:
{{
  "translation": "translated text"
}}
Rules:
- The translation value must be entirely in {target_name} ({target_tag}).
- No markdown code fences.
- No extra keys.
- No explanations.
"""


def _build_translation_prompt(text: str, source_language: str, target_language: str) -> str:
    source_tag, source_name = _describe_language(source_language)
    target_tag, target_name = _describe_language(target_language)
    return (
        f"Translate the following {source_name} ({source_tag}) text into "
        f"{target_name} ({target_tag}) and return JSON only.\n"
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


async def translate_sentence(
    text: str,
    *,
    source_language: str = DEFAULT_SOURCE_LANGUAGE,
    target_language: str = DEFAULT_TARGET_LANGUAGE,
    provider: Any | None = None,
) -> str:
    """Translate one sentence, resolving a provider only when needed."""
    source_tag, _ = _describe_language(source_language)
    target_tag, _ = _describe_language(target_language)
    if source_tag == target_tag:
        # Preserve source text exactly, including intentional leading/trailing
        # whitespace, and avoid a needless (and potentially billable) request.
        return text

    source_text = text.strip()
    if not source_text:
        return ""

    max_attempts = settings.translation_max_retries + 1
    for attempt in range(max_attempts):
        try:
            active_provider = provider
            if active_provider is None:
                with Session(engine) as session:
                    require_provider_capabilities(session, "llm", {ProviderCapability.GENERATE_TEXT, ProviderCapability.GENERATE_JSON})
                    active_provider = get_provider(session, "llm")
            parsed = await asyncio.to_thread(
                _generate_json_with_slot,
                active_provider,
                system_prompt=_build_translation_system_prompt(source_tag, target_tag),
                user_prompt=_build_translation_prompt(source_text, source_tag, target_tag),
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


async def _translate_with_fallback(
    source_text: str,
    provider: Any,
    source_language: str,
    target_language: str,
) -> str:
    try:
        return await translate_sentence(
            source_text,
            source_language=source_language,
            target_language=target_language,
            provider=provider,
        )
    except Exception as error:
        logger.warning(
            "Translation failed for source text prefix '%s': %s",
            source_text[:60],
            error,
        )
        # A failed translation must not turn an English diagnostic into learner
        # content. The caller can keep the blank value or apply its own UI rule.
        return ""


async def translate_sentences(
    texts: Iterable[str],
    *,
    source_language: str = DEFAULT_SOURCE_LANGUAGE,
    target_language: str = DEFAULT_TARGET_LANGUAGE,
) -> List[str]:
    """Translate a material batch through one stable configured provider."""
    text_list = list(texts)
    if not text_list:
        return []

    source_tag, _ = _describe_language(source_language)
    target_tag, _ = _describe_language(target_language)
    if source_tag == target_tag:
        return text_list

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
    try:
        with Session(engine) as session:
            require_provider_capabilities(
                session,
                "llm",
                {ProviderCapability.GENERATE_TEXT, ProviderCapability.GENERATE_JSON},
            )
            provider = get_provider(session, "llm")
    except Exception as error:
        # Translation is enrichment, not a prerequisite for preserving an ASR
        # transcript or a user-authored TTS practice.  Keep the sentence count
        # stable so callers can persist blank translations and retry later.
        logger.warning("Translation provider is unavailable: %s", error)
        return [""] * sentence_count

    results: list[str] = [""] * sentence_count
    for index in range(warmup_count):
        results[index] = await _translate_with_fallback(
            text_list[index], provider, source_tag, target_tag
        )

    remaining_indices = list(range(warmup_count, sentence_count))
    if not remaining_indices:
        return results

    batch_concurrency = max(1, min(target_concurrency, len(remaining_indices)))
    batch_semaphore = asyncio.Semaphore(batch_concurrency)

    async def _translate_remaining(index: int) -> None:
        async with batch_semaphore:
            results[index] = await _translate_with_fallback(
                text_list[index], provider, source_tag, target_tag
            )

    await asyncio.gather(*(_translate_remaining(index) for index in remaining_indices))
    return results
