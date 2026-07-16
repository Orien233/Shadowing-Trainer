from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Capability = Literal["llm", "tts", "asr"]


class AIProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    capability: Capability
    provider_type: str = Field(min_length=1, max_length=100)
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    is_enabled: bool = True
    is_default: bool = False
    extra_config: dict[str, Any] = Field(default_factory=dict)


class AIProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    provider_type: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    is_enabled: bool | None = None
    is_default: bool | None = None
    extra_config: dict[str, Any] | None = None


class AIProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    capability: Capability
    provider_type: str
    base_url: str | None
    api_key_masked: str | None
    model_name: str | None
    is_enabled: bool
    is_default: bool
    extra_config: dict[str, Any]
    capabilities: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProviderTestRequest(BaseModel):
    # Optional unsaved data lets the UI test credentials before persisting them.
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None


class ProviderTestResponse(BaseModel):
    ok: bool
    message: str
    capabilities: list[str] = Field(default_factory=list)


class ASRSceneSettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    material_transcription_use_local: bool
    recording_evaluation_use_local: bool
    updated_at: datetime
    material_transcription_remote_available: bool = False
    material_transcription_missing_capabilities: list[str] = Field(default_factory=list)
    recording_evaluation_remote_available: bool = False
    recording_evaluation_missing_capabilities: list[str] = Field(default_factory=list)


class ASRSceneSettingUpdate(BaseModel):
    material_transcription_use_local: bool | None = None
    recording_evaluation_use_local: bool | None = None
