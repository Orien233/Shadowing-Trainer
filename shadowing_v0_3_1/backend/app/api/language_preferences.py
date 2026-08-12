from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.language_preference import (
    LanguageCatalogItemRead,
    LearningLanguagePreferenceRead,
    LearningLanguagePreferenceUpdate,
)
from app.services.language_catalog import language_catalog_payload
from app.services.learning_language_preference_service import (
    get_or_create_learning_language_preference,
    update_learning_language_preference,
)


router = APIRouter(prefix="/api/languages", tags=["languages"])


@router.get("", response_model=list[LanguageCatalogItemRead])
def list_supported_languages():
    return language_catalog_payload()


@router.get("/preferences", response_model=LearningLanguagePreferenceRead)
def get_language_preferences(session: Session = Depends(get_session)):
    return get_or_create_learning_language_preference(session)


@router.put("/preferences", response_model=LearningLanguagePreferenceRead)
def put_language_preferences(
    payload: LearningLanguagePreferenceUpdate,
    session: Session = Depends(get_session),
):
    return update_learning_language_preference(session, payload)
