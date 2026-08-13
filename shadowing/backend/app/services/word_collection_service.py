import string
import unicodedata
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, asc, desc, func, select

from app.models.word_collection import WordCollection
from app.schemas.word_collection import WordCollectionCreate
from app.services.language_catalog import normalize_language_tag


_EDGE_PUNCTUATION = string.punctuation + "\u2018\u2019\u201c\u201d"
_APOSTROPHES = {"'", "\u2018", "\u2019", "\u201b", "\u2032"}
WordCollectionSortMode = Literal[
    "collected_time_asc",
    "collected_time_desc",
    "alphabetical",
]


class WordAlreadyCollectedError(Exception):
    pass


class EmptyWordCollectionError(ValueError):
    pass


def _is_word_apostrophe(chars: list[str], index: int) -> bool:
    return (
        chars[index] in _APOSTROPHES
        and index > 0
        and index < len(chars) - 1
        and chars[index - 1].isalnum()
        and chars[index + 1].isalnum()
    )


def clean_collected_word_text(word_text: str) -> str:
    chars = list(unicodedata.normalize("NFC", str(word_text or "").strip()))
    cleaned: list[str] = []
    for index, char in enumerate(chars):
        # Combining marks carry meaning in many supported writing systems
        # (for example Arabic tashkeel). Keep a mark only after word content,
        # so surrounding punctuation remains excluded.
        is_combining_mark = unicodedata.category(char).startswith("M") and bool(cleaned)
        if char.isalnum() or is_combining_mark or _is_word_apostrophe(chars, index):
            cleaned.append(char)
    return "".join(cleaned).strip(_EDGE_PUNCTUATION)


def _replace_apostrophes(text: str) -> str:
    normalized = text
    for apostrophe in _APOSTROPHES:
        normalized = normalized.replace(apostrophe, "'")
    return normalized


def normalize_word_text(word_text: str) -> str:
    cleaned = _replace_apostrophes(clean_collected_word_text(word_text))
    return unicodedata.normalize("NFKC", cleaned).casefold()


def normalize_language(language: str | None) -> str:
    return normalize_language_tag(language or "en")


def collect_word(
    session: Session,
    payload: WordCollectionCreate,
) -> WordCollection:
    clean_word_text = clean_collected_word_text(payload.word_text)
    normalized_word = normalize_word_text(clean_word_text)
    if not normalized_word:
        raise EmptyWordCollectionError("Word text is empty after normalization.")

    language = normalize_language(payload.language)
    # SQLite's ``lower`` only handles ASCII.  Use it to narrow by language,
    # then apply the same Unicode-aware canonicalization to legacy keys before
    # deciding whether this is a duplicate (for example Straße/STRASSE).
    language_matches = session.exec(
        select(WordCollection).where(
            func.lower(WordCollection.language) == language.casefold(),
        )
    ).all()
    if any(normalize_word_text(item.normalized_word) == normalized_word for item in language_matches):
        raise WordAlreadyCollectedError

    now = datetime.now(UTC)
    collection = WordCollection(
        material_id=payload.material_id,
        sentence_id=payload.sentence_id,
        word_text=clean_word_text,
        normalized_word=normalized_word,
        language=language,
        translation=payload.translation,
        source_type=payload.source_type or "manual",
        note=payload.note,
        created_at=now,
        updated_at=now,
    )
    session.add(collection)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise WordAlreadyCollectedError from exc

    session.refresh(collection)
    return collection


def list_word_collections(
    session: Session,
    sort: WordCollectionSortMode = "collected_time_asc",
    language: str | None = None,
) -> list[WordCollection]:
    statement = select(WordCollection)
    if language:
        normalized_language = normalize_language(language)
        statement = statement.where(func.lower(WordCollection.language) == normalized_language.casefold())
    if sort == "alphabetical":
        # SQLite's lower()/collation is ASCII-only. Fetch newest-first for a
        # deterministic tie-break, then apply the same Unicode normalization
        # used by collection writes in Python.
        statement = statement.order_by(
            desc(WordCollection.created_at),
            desc(WordCollection.id),
        )
    elif sort == "collected_time_desc":
        statement = statement.order_by(
            asc(WordCollection.created_at),
            asc(WordCollection.id),
        )
    else:
        statement = statement.order_by(
            desc(WordCollection.created_at),
            desc(WordCollection.id),
        )
    items = list(session.exec(statement).all())
    if sort == "alphabetical":
        return sorted(
            items,
            key=lambda item: unicodedata.normalize("NFKC", item.normalized_word).casefold(),
        )
    return items


def delete_word_collection(session: Session, collection_id: int) -> bool:
    collection = session.get(WordCollection, collection_id)
    if not collection:
        return False

    session.delete(collection)
    session.commit()
    return True
