from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.services.language_catalog import normalize_language_tag, normalize_ui_locale


class LanguageCatalogItemRead(BaseModel):
    code: str
    english_name: str
    native_name: str


class LearningLanguagePreferenceUpdate(BaseModel):
    ui_locale: str
    learning_language: str
    translation_language: str

    @field_validator("ui_locale")
    @classmethod
    def validate_ui_locale(cls, value: str) -> str:
        return normalize_ui_locale(value)

    @field_validator("learning_language", "translation_language")
    @classmethod
    def validate_supported_language(cls, value: str) -> str:
        return normalize_language_tag(value)


class LearningLanguagePreferenceRead(LearningLanguagePreferenceUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    updated_at: datetime
