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
    # Empty is a pre-migration compatibility sentinel. New API writes always
    # persist JSON arrays, making the user's declaration authoritative.
    enabled_capabilities: str = Field(default="")
    enabled_formats: str = Field(default="")
    extra_config: str = Field(default="{}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
