from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.services.language_catalog import normalize_language_tag


class WordCollectionCreate(BaseModel):
    material_id: int
    sentence_id: int
    word_text: str
    language: str = "en"
    translation: str | None = None
    source_type: str = "manual"
    note: str | None = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_language_tag(value)


class WordCollectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    sentence_id: int
    word_text: str
    normalized_word: str
    language: str
    translation: str | None
    source_type: str
    note: str | None
    created_at: datetime
    updated_at: datetime


class WordCollectionDeleteResponse(BaseModel):
    deleted: bool
    id: int
