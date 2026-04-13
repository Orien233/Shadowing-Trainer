from datetime import datetime

from pydantic import BaseModel, Field


class SentenceLatestEvaluationRead(BaseModel):
    sentence_id: int
    main_db_recording_id: int | None
    main_db_evaluation_id: int | None
    completeness_score: int
    fluency_score: int
    sync_score: int
    pronunciation_score: int
    overall_score: int
    feedback: str
    suggestion: str
    raw_metrics: str
    created_at: datetime


class MaterialLatestEvaluationsRead(BaseModel):
    material_id: int
    user_id: str
    evaluations: list[SentenceLatestEvaluationRead] = Field(default_factory=list)
