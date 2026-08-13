from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.language_catalog import normalize_language_tag


class TextGenerationRequest(BaseModel):
    word_selection: Literal["random", "manual", "none"] = "none"
    random_word_count: int = Field(default=0, ge=0, le=100)
    word_collection_ids: list[int] = Field(default_factory=list)
    preset_topic: str | None = None
    custom_topic: str | None = None
    target_language: str = "en"
    translation_language: str = "zh-CN"
    difficulty: str = "intermediate"
    desired_length: int = Field(default=180, ge=20, le=5000)

    @field_validator("target_language", "translation_language")
    @classmethod
    def normalize_practice_language(cls, value: str) -> str:
        return normalize_language_tag(value)


class TextPracticeCreate(BaseModel):
    title: str = Field(default="My practice text", min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    target_language: str = "en"
    translation_language: str = "zh-CN"
    difficulty: str | None = None
    topic: str | None = None

    @field_validator("target_language", "translation_language")
    @classmethod
    def normalize_practice_language(cls, value: str) -> str:
        return normalize_language_tag(value)


class TextPracticeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    target_language: str | None = None
    translation_language: str | None = None

    @field_validator("target_language", "translation_language")
    @classmethod
    def normalize_optional_practice_language(cls, value: str | None) -> str | None:
        return normalize_language_tag(value) if value is not None else None


class TTSOptions(BaseModel):
    speed_preset: Literal["slow", "normal", "fast"] = "normal"
    accent: str | None = None
    gender: str | None = None
    voice: str | None = None
    model: str | None = None
    provider_id: int | None = None
    # Normally inherited from TextPractice.target_language when a job is
    # queued. If specified, the service requires the same language so audio
    # and its Material metadata cannot disagree.
    language: str | None = None

    @field_validator("language")
    @classmethod
    def normalize_tts_language(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return normalize_language_tag(value)


class TTSJobResponse(BaseModel):
    text_practice_id: int
    job_id: str
    status: str


class TextPracticeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    source_type: str
    target_language: str
    translation_language: str
    difficulty: str | None
    desired_length: int | None
    topic: str | None
    explanation: str | None
    requested_words: list[str] = Field(default_factory=list)
    used_words: list[str] = Field(default_factory=list)
    unused_words: list[str] = Field(default_factory=list)
    llm_provider_id: int | None
    tts_provider_id: int | None
    tts_status: str
    tts_job_id: str | None
    tts_audio_path: str | None
    material_id: int | None
    created_at: datetime
    updated_at: datetime
