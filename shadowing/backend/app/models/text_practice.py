from datetime import UTC, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class TextPractice(SQLModel, table=True):
    __tablename__ = "text_practices"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    body: str
    source_type: str = Field(index=True)  # llm or import
    target_language: str = "en"
    translation_language: str = "zh-CN"
    difficulty: str | None = None
    desired_length: int | None = None
    topic: str | None = None
    explanation: str | None = None
    requested_words_json: str = "[]"
    used_words_json: str = "[]"
    unused_words_json: str = "[]"
    llm_provider_id: int | None = Field(default=None, index=True)
    tts_provider_id: int | None = Field(default=None, index=True)
    tts_options_json: str = "{}"
    tts_status: str = Field(default="not_requested", index=True)
    tts_job_id: str | None = Field(default=None, index=True)
    tts_audio_path: str | None = None
    material_id: int | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TextPracticeWord(SQLModel, table=True):
    __tablename__ = "text_practice_words"

    id: Optional[int] = Field(default=None, primary_key=True)
    text_practice_id: int = Field(index=True)
    word_collection_id: int | None = Field(default=None, index=True)
    word_text: str
    selection_mode: str = "requested"  # requested, used, unused
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
