import string
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, desc, select

from app.models.word_collection import WordCollection
from app.schemas.word_collection import WordCollectionCreate


_EDGE_PUNCTUATION = string.punctuation + "\u2018\u2019\u201c\u201d"


class WordAlreadyCollectedError(Exception):
    pass


class EmptyWordCollectionError(ValueError):
    pass


def normalize_word_text(word_text: str) -> str:
    return str(word_text or "").strip().lower().strip(_EDGE_PUNCTUATION)


def normalize_language(language: str | None) -> str:
    normalized = str(language or "en").strip().lower()
    return normalized or "en"


def collect_word(
    session: Session,
    payload: WordCollectionCreate,
) -> WordCollection:
    normalized_word = normalize_word_text(payload.word_text)
    if not normalized_word:
        raise EmptyWordCollectionError("Word text is empty after normalization.")

    language = normalize_language(payload.language)
    existing = session.exec(
        select(WordCollection).where(
            WordCollection.normalized_word == normalized_word,
            WordCollection.language == language,
        )
    ).first()
    if existing:
        raise WordAlreadyCollectedError

    now = datetime.utcnow()
    collection = WordCollection(
        material_id=payload.material_id,
        sentence_id=payload.sentence_id,
        word_text=payload.word_text.strip(),
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


def list_word_collections(session: Session) -> list[WordCollection]:
    return list(
        session.exec(
            select(WordCollection).order_by(desc(WordCollection.created_at))
        ).all()
    )


def delete_word_collection(session: Session, collection_id: int) -> bool:
    collection = session.get(WordCollection, collection_id)
    if not collection:
        return False

    session.delete(collection)
    session.commit()
    return True
