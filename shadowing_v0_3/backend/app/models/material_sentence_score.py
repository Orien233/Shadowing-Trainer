from datetime import datetime
from typing import Optional

from sqlmodel import Field, Index, SQLModel


class MaterialSentenceScore(SQLModel, table=True):
    __tablename__ = "material_sentence_score"
    __table_args__ = (
        Index(
            "ix_mss_user_material_sentence_created",
            "user_id",
            "material_id",
            "sentence_id",
            "created_at",
        ),
        Index(
            "ix_mss_user_material_created",
            "user_id",
            "material_id",
            "created_at",
        ),
        Index("ix_mss_main_db_evaluation_id", "main_db_evaluation_id"),
        Index("ix_mss_main_db_recording_id", "main_db_recording_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(default="default", index=True, max_length=64)
    material_id: int = Field(index=True)
    sentence_id: int = Field(index=True)
    main_db_recording_id: int | None = Field(default=None)
    main_db_evaluation_id: int | None = Field(default=None)
    completeness_score: int
    fluency_score: int
    sync_score: int
    pronunciation_score: int
    overall_score: int
    feedback: str
    suggestion: str
    raw_metrics: str
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
