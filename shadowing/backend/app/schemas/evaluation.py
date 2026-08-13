from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recording_id: int
    completeness_score: int
    fluency_score: int
    sync_score: int
    pronunciation_score: int
    overall_score: int
    feedback: str
    suggestion: str
    raw_metrics: str
    word_alignment: dict[str, Any] | None = None
    created_at: datetime
