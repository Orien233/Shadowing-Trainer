from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session

from app.models.learning_language_preference import LearningLanguagePreference
from app.schemas.language_preference import LearningLanguagePreferenceUpdate


DEFAULT_PREFERENCE_ID = 1


def get_or_create_learning_language_preference(session: Session) -> LearningLanguagePreference:
    preference = session.get(LearningLanguagePreference, DEFAULT_PREFERENCE_ID)
    if preference is not None:
        return preference
    preference = LearningLanguagePreference(id=DEFAULT_PREFERENCE_ID)
    session.add(preference)
    session.commit()
    session.refresh(preference)
    return preference


def update_learning_language_preference(
    session: Session,
    payload: LearningLanguagePreferenceUpdate,
) -> LearningLanguagePreference:
    preference = get_or_create_learning_language_preference(session)
    preference.ui_locale = payload.ui_locale
    preference.learning_language = payload.learning_language
    preference.translation_language = payload.translation_language
    preference.updated_at = datetime.now(UTC)
    session.add(preference)
    session.commit()
    session.refresh(preference)
    return preference
