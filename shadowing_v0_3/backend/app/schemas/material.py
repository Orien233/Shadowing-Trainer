from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MaterialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    file_type: str
    original_path: str
    audio_path: str | None
    duration: float | None
    status: str
    created_at: datetime


class MaterialDetail(MaterialRead):
    sentence_count: int = 0
