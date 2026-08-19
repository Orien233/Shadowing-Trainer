from __future__ import annotations

import json
import random
import re
import unicodedata
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.models.text_practice import TextPractice
from app.models.word_collection import WordCollection
from app.schemas.text_practice import TextGenerationRequest, TextPracticeCreate
from app.services.ai.audio_types import ProviderCapability
from app.services.provider_factory import get_provider, require_provider_capabilities
from app.services.language_catalog import get_language_descriptor, normalize_language_tag

PRESET_TOPICS = {"daily_life", "travel", "workplace", "campus", "news", "story"}

SYSTEM_PROMPT = """You create concise, natural shadowing practice texts. Return only a JSON object with title, body, used_words, unused_words, and explanation. The body must be coherent and suited to spoken practice; selected words should appear naturally, never as a word list."""

PRACTICE_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "body", "used_words", "unused_words"],
    "properties": {
        "title": {"type": "string"},
        "body": {"type": "string"},
        "used_words": {"type": "array", "items": {"type": "string"}},
        "unused_words": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
    },
}


def _select_collections(session: Session, request: TextGenerationRequest) -> list[WordCollection]:
    target_language = normalize_language_tag(request.target_language)
    if request.word_selection == "manual":
        ids = list(dict.fromkeys(request.word_collection_ids))
        if not ids:
            return []
        items = list(session.exec(select(WordCollection).where(WordCollection.id.in_(ids))).all())
        found = {item.id for item in items}
        missing = [item_id for item_id in ids if item_id not in found]
        if missing:
            raise ValueError("One or more selected collected words no longer exist.")
        mismatched = [item.word_text for item in items if not _collection_matches_language(item, target_language)]
        if mismatched:
            raise ValueError("Selected collected words must use the target language.")
        return items
    if request.word_selection == "random":
        all_items = [
            item for item in session.exec(select(WordCollection)).all()
            if _collection_matches_language(item, target_language)
        ]
        if request.random_word_count > len(all_items):
            raise ValueError("Requested random word count exceeds the collection size.")
        return random.sample(all_items, request.random_word_count)
    return []


def _collection_matches_language(item: WordCollection, target_language: str) -> bool:
    try:
        return normalize_language_tag(item.language) == target_language
    except ValueError:
        return False


def _topic(request: TextGenerationRequest) -> str:
    if request.custom_topic and request.custom_topic.strip():
        return request.custom_topic.strip()
    if request.preset_topic:
        if request.preset_topic not in PRESET_TOPICS:
            raise ValueError("Unsupported preset topic.")
        return request.preset_topic.replace("_", " ")
    return "general conversation"


def _normalize_words(value: object, requested: list[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    requested_lookup = {_word_key(word): word for word in requested}
    result: list[str] = []
    for item in value:
        word = str(item).strip()
        key = _word_key(word)
        if word and key in requested_lookup and requested_lookup[key] not in result:
            result.append(requested_lookup[key])
    return result


def _word_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


def _word_appears_in_body(word: str, body: str, language: str) -> bool:
    word_key = _word_key(word)
    body_key = _word_key(body)
    if not word_key:
        return False
    primary_language = normalize_language_tag(language).split("-", 1)[0]
    if primary_language in {"zh", "ja", "ko"}:
        return word_key in body_key
    # Avoid treating a short collected word as used merely because it appears
    # inside another word (for example ``he`` in ``the``). Python's Unicode
    # ``\w`` boundary covers the alphabetic scripts in the supported catalog.
    return re.search(rf"(?<!\w){re.escape(word_key)}(?!\w)", body_key) is not None


def _build_prompt(request: TextGenerationRequest, words: list[str], topic: str) -> str:
    language = get_language_descriptor(request.target_language)
    explanation_language = get_language_descriptor(request.translation_language)
    return json.dumps({"target_language": {"code": language.code, "name": language.english_name, "native_name": language.native_name}, "explanation_language": {"code": explanation_language.code, "name": explanation_language.english_name}, "difficulty": request.difficulty, "approximate_length": request.desired_length, "topic": topic, "selected_words": words, "requirements": f"Write the title and body entirely in {language.english_name}. Write the optional explanation in {explanation_language.english_name}. Create a continuous spoken-practice passage. Use selected words naturally where possible. Do not include markdown."}, ensure_ascii=False)


def create_generated_practice(session: Session, request: TextGenerationRequest) -> TextPractice:
    collections = _select_collections(session, request)
    requested_words = [item.word_text for item in collections]
    topic = _topic(request)
    provider_record = require_provider_capabilities(
        session,
        "llm",
        {ProviderCapability.GENERATE_TEXT, ProviderCapability.GENERATE_JSON},
    )
    provider = get_provider(session, "llm", provider_record.id)
    prompt = _build_prompt(request, requested_words, topic)
    try:
        payload = provider.generate_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            json_schema=PRACTICE_RESULT_SCHEMA,
        )
    except TypeError as exc:
        # A third-party legacy implementation can reject the new optional
        # parameter before issuing a request.  Retrying without it preserves
        # compatibility without generating a second paid response.
        if "json_schema" not in str(exc):
            raise
        payload = provider.generate_json(system_prompt=SYSTEM_PROMPT, user_prompt=prompt)
    except ValueError as exc:
        raise ValueError(
            "LLM returned invalid structured practice JSON. Please retry after checking the provider's JSON capability."
        ) from exc
    title = str(payload.get("title", "Generated practice")).strip() or "Generated practice"
    body = str(payload.get("body", "")).strip()
    if not body:
        raise ValueError("LLM response did not contain a usable body.")
    used_words = _normalize_words(payload.get("used_words"), requested_words)
    unused_words = _normalize_words(payload.get("unused_words"), requested_words)
    for word in requested_words:
        if _word_appears_in_body(word, body, request.target_language) and word not in used_words:
            used_words.append(word)
    unused_words = [word for word in requested_words if word not in used_words] if not unused_words else unused_words
    practice = TextPractice(title=title, body=body, source_type="llm", target_language=request.target_language, translation_language=request.translation_language, difficulty=request.difficulty, desired_length=request.desired_length, topic=topic, explanation=str(payload.get("explanation", "")).strip() or None, requested_words_json=json.dumps(requested_words, ensure_ascii=False), used_words_json=json.dumps(used_words, ensure_ascii=False), unused_words_json=json.dumps(unused_words, ensure_ascii=False), llm_provider_id=provider_record.id)
    session.add(practice)
    session.commit()
    session.refresh(practice)
    return practice


def create_imported_practice(session: Session, payload: TextPracticeCreate) -> TextPractice:
    now = datetime.now(UTC)
    practice = TextPractice(title=payload.title.strip(), body=payload.body.strip(), source_type="import", target_language=payload.target_language, translation_language=payload.translation_language, difficulty=payload.difficulty, topic=payload.topic, created_at=now, updated_at=now)
    session.add(practice)
    session.commit()
    session.refresh(practice)
    return practice


def update_practice(session: Session, practice: TextPractice, *, title: str | None, body: str | None, target_language: str | None = None, translation_language: str | None = None) -> TextPractice:
    if title is not None:
        practice.title = title.strip()
    if body is not None:
        practice.body = body.strip()
    if target_language is not None:
        practice.target_language = target_language
    if translation_language is not None:
        practice.translation_language = translation_language
    if title is not None or body is not None or target_language is not None or translation_language is not None:
        practice.tts_status = "not_requested"
        # Queued/running TTS jobs are immutable snapshots. Clearing ownership
        # makes an older worker obsolete, so it cannot publish stale audio.
        practice.tts_job_id = None
        practice.tts_audio_path = None
        practice.material_id = None
    practice.updated_at = datetime.now(UTC)
    session.add(practice)
    session.commit()
    session.refresh(practice)
    return practice


def json_words(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in value] if isinstance(value, list) else []
