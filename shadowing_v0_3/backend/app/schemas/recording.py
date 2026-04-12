from pydantic import BaseModel

from app.schemas.evaluation import EvaluationRead


class RecordingUploadResponse(BaseModel):
    recording_id: int
    evaluation: EvaluationRead
