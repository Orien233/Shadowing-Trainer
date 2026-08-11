from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Capability = Literal["llm", "tts", "asr"]
VerificationLevel = Literal["network", "configuration"]


class ProviderConfigFieldRead(BaseModel):
    """A safe, adapter-declared configuration field shown by the settings UI.

    Provider descriptors own this schema.  It deliberately describes only
    non-secret fields; credentials continue to live in ``api_key`` and are
    never included in a catalog or read response.
    """

    key: str
    label: str
    field_type: Literal["string", "number", "boolean", "select"] = "string"
    required: bool = False
    options: list[str] = Field(default_factory=list)
    default: Any | None = None
    placeholder: str | None = None
    help_text: str | None = None


class ProviderVoiceRead(BaseModel):
    id: str
    name: str
    languages: list[str] = Field(default_factory=list)
    gender: str | None = None
    accent: str | None = None
    styles: list[str] = Field(default_factory=list)
    preview_url: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderCatalogItemRead(BaseModel):
    key: str
    label: str
    kind: Capability
    capabilities: list[str] = Field(default_factory=list)
    available_capabilities: list[str] = Field(default_factory=list)
    available_formats: list[str] = Field(default_factory=list)
    preset: bool = True
    preset_defaults: dict[str, Any] = Field(default_factory=dict)
    endpoint_mode: Literal["base_url", "full_endpoint", "none"] = "base_url"
    endpoint_hint: str | None = None
    required_fields: list[str] = Field(default_factory=list)
    config_fields: list[ProviderConfigFieldRead] = Field(default_factory=list)
    voice_presets: list[ProviderVoiceRead] = Field(default_factory=list)
    docs_url: str | None = None
    # Catalog descriptors can include richer no-cost test metadata.  The
    # actual test response exposes the concise ``verification_level`` field.
    test_strategy: dict[str, Any] | VerificationLevel = "configuration"


class AIProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    capability: Capability
    provider_type: str = Field(min_length=1, max_length=100)
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    is_enabled: bool = True
    is_default: bool = False
    enabled_capabilities: list[str] = Field(default_factory=list)
    enabled_formats: list[str] = Field(default_factory=list)
    extra_config: dict[str, Any] = Field(default_factory=dict)


class AIProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    provider_type: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    is_enabled: bool | None = None
    is_default: bool | None = None
    enabled_capabilities: list[str] | None = None
    enabled_formats: list[str] | None = None
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
    available_capabilities: list[str] = Field(default_factory=list)
    enabled_capabilities: list[str] = Field(default_factory=list)
    available_formats: list[str] = Field(default_factory=list)
    enabled_formats: list[str] = Field(default_factory=list)
    is_deprecated: bool = False
    created_at: datetime
    updated_at: datetime


class ProviderTestRequest(BaseModel):
    # Optional unsaved data lets the UI test credentials before persisting them.
    # ``capability`` and ``provider_type`` make POST /providers/test usable for
    # a draft; when omitted, POST /{id}/test uses the saved record.
    name: str | None = None
    capability: Capability | None = None
    provider_type: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    extra_config: dict[str, Any] | None = None
    enabled_capabilities: list[str] | None = None
    enabled_formats: list[str] | None = None


class ProviderTestResponse(BaseModel):
    ok: bool
    message: str
    capabilities: list[str] = Field(default_factory=list)
    available_capabilities: list[str] = Field(default_factory=list)
    enabled_capabilities: list[str] = Field(default_factory=list)
    available_formats: list[str] = Field(default_factory=list)
    enabled_formats: list[str] = Field(default_factory=list)
    verification_level: VerificationLevel = "configuration"


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
