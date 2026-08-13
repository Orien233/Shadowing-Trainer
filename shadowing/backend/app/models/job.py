from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel


class Job(SQLModel, table=True):
    """A durable, single-process-friendly task record stored in app.db."""

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    kind: str = Field(index=True)
    status: str = Field(default="queued", index=True)
    stage: str = Field(default="queued")
    progress: int = Field(default=0)
    payload: str = Field(default="{}")
    result: str | None = None
    error_message: str | None = None
    worker_id: str | None = Field(default=None, index=True)
    attempts: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None
