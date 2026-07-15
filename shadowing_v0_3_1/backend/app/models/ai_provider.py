from datetime import UTC, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class AIProvider(SQLModel, table=True):
    __tablename__ = "ai_providers"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    capability: str = Field(index=True)  # llm, tts, asr
    provider_type: str
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    is_enabled: bool = Field(default=True, index=True)
    is_default: bool = Field(default=False, index=True)
    extra_config: str = Field(default="{}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
