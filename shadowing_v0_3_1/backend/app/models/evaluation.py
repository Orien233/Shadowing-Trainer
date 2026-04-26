import json

from datetime import datetime
from typing import Any, Optional

from sqlmodel import Field, SQLModel


class Evaluation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    recording_id: int = Field(index=True)
    completeness_score: int
    fluency_score: int
    sync_score: int
    pronunciation_score: int
    overall_score: int
    feedback: str
    suggestion: str
    raw_metrics: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def word_alignment(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.raw_metrics)
        except Exception:
            return None

        word_alignment = payload.get("word_alignment")
        if isinstance(word_alignment, dict):
            return word_alignment
        return None
