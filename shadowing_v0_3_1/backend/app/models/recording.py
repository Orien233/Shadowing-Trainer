from datetime import UTC, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Recording(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sentence_id: int = Field(index=True)
    audio_path: str
    duration: float | None = None
    asr_text: str | None = None
    status: str = Field(default="queued", index=True)
    error_message: str | None = None
    job_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
