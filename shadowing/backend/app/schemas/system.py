from pydantic import BaseModel, Field


class FileCleanupError(BaseModel):
    path: str
    reason: str


class RecordingCleanupResponse(BaseModel):
    target_dir: str
    total_files: int
    deleted_files: int
    failed_files: list[FileCleanupError] = Field(default_factory=list)


class ShutdownResponse(BaseModel):
    detail: str
