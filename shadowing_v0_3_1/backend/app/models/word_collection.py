from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel


class WordCollection(SQLModel, table=True):
    __tablename__ = "word_collections"
    __table_args__ = (
        UniqueConstraint(
            "normalized_word",
            "language",
            name="uq_word_collections_normalized_language",
        ),
        Index("ix_word_collections_created_at", "created_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    material_id: int = Field(index=True)
    sentence_id: int = Field(index=True)
    word_text: str
    normalized_word: str = Field(index=True)
    language: str = Field(default="en", index=True)
    translation: str | None = None
    source_type: str = Field(default="manual")
    note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
