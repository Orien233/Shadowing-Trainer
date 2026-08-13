import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    status: str
    stage: str
    progress: int
    result: dict[str, Any] | None = None
    error_message: str | None = None
    attempts: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @field_validator("result", mode="before")
    @classmethod
    def parse_result(cls, value: Any) -> dict[str, Any] | None:
        if value is None or isinstance(value, dict):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
