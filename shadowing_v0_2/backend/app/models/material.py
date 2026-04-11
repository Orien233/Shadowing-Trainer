from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Material(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    file_type: str
    original_path: str
    audio_path: str | None = None
    duration: float | None = None
    status: str = "uploaded"
    processing_owner: str | None = None
    processing_started_at: datetime | None = None
    processing_heartbeat_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
