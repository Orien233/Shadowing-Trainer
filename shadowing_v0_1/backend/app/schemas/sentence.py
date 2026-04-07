from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SentenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    display_order: int
    start_time: float
    end_time: float
    source_text: str
    translation: str | None
    created_at: datetime
