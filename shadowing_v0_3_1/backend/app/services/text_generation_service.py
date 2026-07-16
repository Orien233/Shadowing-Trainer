from __future__ import annotations

import json
import random
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.models.text_practice import TextPractice, TextPracticeWord
from app.models.word_collection import WordCollection
from app.schemas.text_practice import TextGenerationRequest, TextPracticeCreate
from app.services.ai.llm.openai_compatible import extract_json_object
from app.services.ai.audio_types import ProviderCapability
from app.services.provider_factory import get_provider, require_provider_capabilities

PRESET_TOPICS = {"daily_life", "travel", "workplace", "campus", "news", "story"}

SYSTEM_PROMPT = """You create concise, natural shadowing practice texts. Return only a JSON object with title, body, used_words, unused_words, and explanation. The body must be coherent and suited to spoken practice; selected words should appear naturally, never as a word list."""


def _select_collections(session: Session, request: TextGenerationRequest) -> list[WordCollection]:
    if request.word_selection == "manual":
        ids = list(dict.fromkeys(request.word_collection_ids))
        if not ids:
            return []
        items = list(session.exec(select(WordCollection).where(WordCollection.id.in_(ids))).all())
        found = {item.id for item in items}
        missing = [item_id for item_id in ids if item_id not in found]
        if missing:
            raise ValueError("One or more selected collected words no longer exist.")
        return items
    if request.word_selection == "random":
        all_items = list(session.exec(select(WordCollection)).all())
        if request.random_word_count > len(all_items):
            raise ValueError("Requested random word count exceeds the collection size.")
        return random.sample(all_items, request.random_word_count)
    return []


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
    requested_lookup = {word.lower(): word for word in requested}
    result: list[str] = []
    for item in value:
        word = str(item).strip()
        if word and word.lower() in requested_lookup and requested_lookup[word.lower()] not in result:
            result.append(requested_lookup[word.lower()])
    return result


def _build_prompt(request: TextGenerationRequest, words: list[str], topic: str) -> str:
    return json.dumps({"target_language": request.target_language, "difficulty": request.difficulty, "approximate_length": request.desired_length, "topic": topic, "selected_words": words, "requirements": "Write a continuous spoken-practice passage. Use selected words naturally where possible. Do not include markdown."}, ensure_ascii=False)


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
        payload = provider.generate_json(system_prompt=SYSTEM_PROMPT, user_prompt=prompt)
    except ValueError:
        # Compatible endpoints occasionally ignore JSON mode. Preserve a usable result
        # if they return a JSON object wrapped in prose.
        raw = provider.generate_text(system_prompt=SYSTEM_PROMPT, user_prompt=prompt, temperature=0.3)
        payload = extract_json_object(raw)
    title = str(payload.get("title", "Generated practice")).strip() or "Generated practice"
    body = str(payload.get("body", "")).strip()
    if not body:
        raise ValueError("LLM response did not contain a usable body.")
    used_words = _normalize_words(payload.get("used_words"), requested_words)
    unused_words = _normalize_words(payload.get("unused_words"), requested_words)
    for word in requested_words:
        if word.lower() in body.lower() and word not in used_words:
            used_words.append(word)
    unused_words = [word for word in requested_words if word not in used_words] if not unused_words else unused_words
    practice = TextPractice(title=title, body=body, source_type="llm", target_language=request.target_language, difficulty=request.difficulty, desired_length=request.desired_length, topic=topic, explanation=str(payload.get("explanation", "")).strip() or None, requested_words_json=json.dumps(requested_words, ensure_ascii=False), used_words_json=json.dumps(used_words, ensure_ascii=False), unused_words_json=json.dumps(unused_words, ensure_ascii=False), llm_provider_id=provider_record.id)
    session.add(practice)
    session.flush()
    for item in collections:
        mode = "used" if item.word_text in used_words else "unused"
        session.add(TextPracticeWord(text_practice_id=practice.id, word_collection_id=item.id, word_text=item.word_text, selection_mode=mode))
    session.commit()
    session.refresh(practice)
    return practice


def create_imported_practice(session: Session, payload: TextPracticeCreate) -> TextPractice:
    now = datetime.now(UTC)
    practice = TextPractice(title=payload.title.strip(), body=payload.body.strip(), source_type="import", target_language=payload.target_language, difficulty=payload.difficulty, topic=payload.topic, created_at=now, updated_at=now)
    session.add(practice)
    session.commit()
    session.refresh(practice)
    return practice


def update_practice(session: Session, practice: TextPractice, *, title: str | None, body: str | None) -> TextPractice:
    if title is not None:
        practice.title = title.strip()
    if body is not None:
        practice.body = body.strip()
        practice.tts_status = "not_requested"
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
