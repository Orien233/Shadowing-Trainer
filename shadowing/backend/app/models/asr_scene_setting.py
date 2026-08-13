from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ASRSceneSetting(SQLModel, table=True):
    __tablename__ = "asr_scene_settings"

    id: int = Field(default=1, primary_key=True)
    material_transcription_use_local: bool = True
    recording_evaluation_use_local: bool = True
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
