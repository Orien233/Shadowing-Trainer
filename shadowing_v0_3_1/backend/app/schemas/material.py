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
    job_id: str | None = None
    processing_stage: str | None = None
    processing_progress: int = 0
    error_message: str | None = None
    created_at: datetime


class MaterialDetail(MaterialRead):
    sentence_count: int = 0
