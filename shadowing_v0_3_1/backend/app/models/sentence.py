from datetime import UTC, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Sentence(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    material_id: int = Field(index=True)
    display_order: int = Field(index=True)
    start_time: float
    end_time: float
    original_start_time: float | None = None
    original_end_time: float | None = None
    clip_audio_path: str | None = None
    clip_duration: float | None = None
    source_text: str
    translation: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
