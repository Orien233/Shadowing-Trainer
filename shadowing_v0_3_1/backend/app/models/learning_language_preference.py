from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class LearningLanguagePreference(SQLModel, table=True):
    """The single, local user's language defaults (the row is always id=1)."""

    __tablename__ = "learning_language_preferences"

    id: int = Field(default=1, primary_key=True)
    ui_locale: str = Field(default="zh-CN")
    learning_language: str = Field(default="en")
    translation_language: str = Field(default="zh-CN")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
