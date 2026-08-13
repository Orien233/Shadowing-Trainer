"""Configuration APIs for static, descriptor-driven AI providers."""

from __future__ import annotations

import json
import tempfile
import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.ai_provider import AIProvider
from app.schemas.ai_provider import (
    AIProviderCreate,
    AIProviderRead,
    AIProviderUpdate,
    ASRSceneSettingRead,
    ASRSceneSettingUpdate,
    LocalASRStatusRead,
    LocalASRTestRequest,
    ProviderCatalogItemRead,
    ProviderTestRequest,
    ProviderTestResponse,
    ProviderVoiceRead,
)
from app.services.ai.adapter_registry import AdapterDescriptor, catalog_payload
from app.services.ai.audio_types import ProviderCapability
from app.services.ai.tts.base import TTSRequest
from app.services.asr_router import (
    MATERIAL_TRANSCRIPTION,
    RECORDING_EVALUATION,
    enforce_scene_capabilities,
    get_or_create_scene_settings,
    get_scene_availability,
    get_scene_settings_for_read,
    resolve_scene_route,
)
from app.services.local_whisper_runtime import (
    get_local_whisper_status,
    load_local_whisper_model,
    release_local_whisper_model,
)
from app.services.provider_factory import (
    ProviderConfigurationError,
    create_provider,
    get_declared_capabilities,
    get_enabled_capabilities,
    get_provider_descriptor,
    parse_extra_config,
    parse_string_list,
    public_extra_config,
    validate_provider_configuration,
)
from app.services.provider_security import redact_provider_error, sanitize_url


router = APIRouter(prefix="/api/providers", tags=["providers"])


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 4:
        return "*" * len(key)
    return f"{key[:2]}{'*' * max(4, len(key) - 6)}{key[-4:]}"


def _descriptor_or_none(provider: AIProvider) -> AdapterDescriptor | None:
    try:
        return get_provider_descriptor(provider.capability, provider.provider_type)
    except ProviderConfigurationError:
        return None


def _read(provider: AIProvider) -> AIProviderRead:
    descriptor = _descriptor_or_none(provider)
    extra = (
        public_extra_config(descriptor, parse_extra_config(provider.extra_config))
        if descriptor else {}
    )
    return AIProviderRead(
        id=provider.id,
        name=provider.name,
        capability=provider.capability,
        # Keep unknown legacy values visible for repair; known aliases are
        # projected to their canonical catalog key for the dynamic UI.
        provider_type=descriptor.canonical_key if descriptor else provider.provider_type,
        base_url=sanitize_url(provider.base_url),
        api_key_masked=_mask_key(provider.api_key),
        model_name=provider.model_name,
        is_enabled=provider.is_enabled,
        is_default=provider.is_default,
    extra_config=extra,
        capabilities=sorted(item.value for item in get_enabled_capabilities(provider)),
        available_capabilities=sorted(item.value for item in get_declared_capabilities(provider)),
        enabled_capabilities=sorted(parse_string_list(provider.enabled_capabilities)),
        available_formats=list(descriptor.format_options) if descriptor else [],
        enabled_formats=sorted(parse_string_list(provider.enabled_formats)),
        is_deprecated=descriptor is None,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


def _scene_read(session: Session) -> ASRSceneSettingRead:
    # A GET must not create or reconcile database rows.  Effective flags still
    # make a capability-incompatible remote mode appear as forced-local.
    value = get_scene_settings_for_read(session)
    material = get_scene_availability(session, MATERIAL_TRANSCRIPTION)
    recording = get_scene_availability(session, RECORDING_EVALUATION)
    material_route = resolve_scene_route(session, MATERIAL_TRANSCRIPTION, value)
    recording_route = resolve_scene_route(session, RECORDING_EVALUATION, value)
    return ASRSceneSettingRead(
        material_transcription_use_local=material_route == "local",
        recording_evaluation_use_local=recording_route == "local",
        updated_at=value.updated_at,
        material_transcription_remote_available=material.remote_available,
        material_transcription_missing_capabilities=list(material.missing_capabilities),
        material_transcription_local_available=material.local_available,
        material_transcription_local_unavailable_reason=material.local_unavailable_reason,
        material_transcription_effective_route=material_route,
        material_transcription_available=material_route != "unavailable",
        recording_evaluation_remote_available=recording.remote_available,
        recording_evaluation_missing_capabilities=list(recording.missing_capabilities),
        recording_evaluation_local_available=recording.local_available,
        recording_evaluation_local_unavailable_reason=recording.local_unavailable_reason,
        recording_evaluation_effective_route=recording_route,
        recording_evaluation_available=recording_route != "unavailable",
    )


def _clear_other_defaults(session: Session, capability: str, current_id: int | None = None) -> None:
    statement = select(AIProvider).where(
        AIProvider.capability == capability,
        AIProvider.is_default == True,  # noqa: E712
    )
    for provider in session.exec(statement).all():
        if provider.id != current_id:
            provider.is_default = False
            session.add(provider)


def _reconcile_asr_scenes(session: Session, capability: str) -> None:
    """Persist forced-local safety after a remote ASR config mutation."""
    if capability == "asr":
        enforce_scene_capabilities(session, get_or_create_scene_settings(session))


def _trim(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _make_provider(
    *,
    name: str,
    capability: str,
    provider_type: str,
    base_url: str | None,
    api_key: str | None,
    model_name: str | None,
    is_enabled: bool,
    is_default: bool,
    extra_config: Mapping[str, Any] | None,
    enabled_capabilities: list[str] | set[str] | None = None,
    enabled_formats: list[str] | set[str] | None = None,
    source_id: int | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> AIProvider:
    try:
        descriptor, cleaned_extra = validate_provider_configuration(
            capability=capability,
            provider_type=provider_type,
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            extra_config=extra_config,
            enabled_capabilities={str(item).lower() for item in (enabled_capabilities or [])},
            enabled_formats={str(item).lower() for item in (enabled_formats or [])},
        )
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if is_enabled and not enabled_capabilities:
        raise HTTPException(status_code=422, detail="An enabled provider must declare at least one capability.")
    if is_default and not is_enabled:
        raise HTTPException(status_code=422, detail="A default provider must be enabled.")
    return AIProvider(
        id=source_id,
        name=name.strip(),
        capability=capability,
        provider_type=descriptor.canonical_key,
        base_url=_trim(base_url),
        api_key=_trim(api_key),
        model_name=_trim(model_name),
        is_enabled=is_enabled,
        is_default=is_default,
        enabled_capabilities=json.dumps(sorted({str(item).lower() for item in (enabled_capabilities or [])})),
        enabled_formats=json.dumps(sorted({str(item).lower() for item in (enabled_formats or [])})),
        extra_config=json.dumps(cleaned_extra, ensure_ascii=False),
        created_at=created_at or datetime.now(UTC),
        updated_at=updated_at or datetime.now(UTC),
    )


def _candidate_for_update(provider: AIProvider, payload: AIProviderUpdate) -> AIProvider:
    changes = payload.model_dump(exclude_unset=True)
    candidate_type = changes.get("provider_type", provider.provider_type)
    # Blank API-key edits intentionally retain the stored key.
    requested_key = changes.get("api_key")
    candidate_key = provider.api_key if not requested_key or not str(requested_key).strip() else str(requested_key)
    descriptor = _descriptor_or_none(
        AIProvider(
            name=provider.name,
            capability=provider.capability,
            provider_type=candidate_type,
        )
    )
    existing_extra = parse_extra_config(provider.extra_config)
    if descriptor:
        existing_extra = public_extra_config(descriptor, existing_extra)
    extra = changes.get("extra_config", existing_extra)
    return _make_provider(
        name=changes.get("name", provider.name),
        capability=provider.capability,
        provider_type=candidate_type,
        base_url=changes.get("base_url", provider.base_url),
        api_key=candidate_key,
        model_name=changes.get("model_name", provider.model_name),
        is_enabled=changes.get("is_enabled", provider.is_enabled),
        is_default=changes.get("is_default", provider.is_default),
        extra_config=extra,
        enabled_capabilities=changes.get("enabled_capabilities", parse_string_list(provider.enabled_capabilities)),
        enabled_formats=changes.get("enabled_formats", parse_string_list(provider.enabled_formats)),
        source_id=provider.id,
        created_at=provider.created_at,
    )


def _verification_level(descriptor: AdapterDescriptor) -> str:
    strategy = descriptor.test_strategy
    value: Any = getattr(strategy, "verification_level", None)
    if value is None and isinstance(strategy, Mapping):
        value = strategy.get("verification_level")
    return "network" if value == "network" else "configuration"


def _test_response(
    *,
    provider: AIProvider,
    descriptor: AdapterDescriptor,
    ok: bool,
    message: str,
    verification_level: str,
    billable: bool = False,
) -> ProviderTestResponse:
    capabilities = sorted(item.value for item in get_enabled_capabilities(provider))
    return ProviderTestResponse(
        ok=ok,
        message=message,
        capabilities=capabilities,
        available_capabilities=sorted(item.value for item in descriptor.capabilities),
        enabled_capabilities=capabilities,
        available_formats=list(descriptor.format_options),
        enabled_formats=sorted(parse_string_list(provider.enabled_formats)),
        verification_level=verification_level,
        billable=billable,
    )


def _write_silent_wav() -> Path:
    """Create a minimal safe ASR test input without using user recordings."""
    handle = tempfile.NamedTemporaryFile(prefix="shadowing-asr-test-", suffix=".wav", delete=False)
    path = Path(handle.name)
    handle.close()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x00\x00" * 3200)  # 0.2 s of silence
    return path


def _run_inference_test(provider: AIProvider, instance: Any) -> str:
    capabilities = get_enabled_capabilities(provider)
    if provider.capability == "llm":
        if ProviderCapability.GENERATE_TEXT not in capabilities:
            raise ProviderConfigurationError("A live LLM test requires generate_text to be enabled.")
        instance.generate_text(
            system_prompt="You are a connection test. Respond with exactly OK.",
            user_prompt="Return OK.",
            temperature=0,
        )
        return "A small live LLM generation request succeeded."
    if provider.capability == "tts":
        if ProviderCapability.SYNTHESIZE not in capabilities:
            raise ProviderConfigurationError("A live TTS test requires synthesize to be enabled.")
        result = instance.synthesize(
            TTSRequest(text="Connection test.", model=provider.model_name or None)
        )
        if not result.audio:
            raise ProviderConfigurationError("The provider returned empty test audio.")
        return "A small live TTS synthesis request succeeded."
    if provider.capability == "asr":
        if ProviderCapability.TRANSCRIBE not in capabilities:
            raise ProviderConfigurationError("A live ASR test requires transcribe to be enabled.")
        path = _write_silent_wav()
        try:
            instance.transcribe(str(path))
        finally:
            path.unlink(missing_ok=True)
        return "A small live ASR transcription request succeeded."
    raise ProviderConfigurationError("Unsupported provider capability for a live test.")


def _test_provider(provider: AIProvider, test_mode: str = "configuration") -> ProviderTestResponse:
    descriptor = get_provider_descriptor(provider.capability, provider.provider_type)
    try:
        instance = create_provider(provider)
        if test_mode == "configuration":
            return _test_response(
                provider=provider,
                descriptor=descriptor,
                ok=True,
                message="Provider configuration is valid; no network or billable request was made.",
                verification_level="configuration",
            )
        if test_mode == "network":
            return _test_response(
                provider=provider,
                descriptor=descriptor,
                ok=True,
                message=instance.test_connection(),
                verification_level=_verification_level(descriptor),
            )
        if test_mode == "inference":
            return _test_response(
                provider=provider,
                descriptor=descriptor,
                ok=True,
                message=_run_inference_test(provider, instance),
                verification_level="inference",
                billable=True,
            )
        raise ProviderConfigurationError(f"Unsupported provider test mode: {test_mode}.")
    except Exception as exc:  # Expected connection/configuration failures are data, not a 500.
        return _test_response(
            provider=provider,
            descriptor=descriptor,
            ok=False,
            message=f"{test_mode.capitalize()} test failed: {type(exc).__name__}: {redact_provider_error(exc, provider.api_key)}",
            verification_level="inference" if test_mode == "inference" else (
                _verification_level(descriptor) if test_mode == "network" else "configuration"
            ),
            billable=test_mode == "inference",
        )


def _voice_response(item: Mapping[str, Any]) -> ProviderVoiceRead:
    locale = item.get("locale")
    languages = item.get("languages")
    if not isinstance(languages, list):
        languages = [str(locale)] if locale else []
    return ProviderVoiceRead(
        id=str(item.get("id", "")),
        name=str(item.get("name") or item.get("id") or ""),
        languages=[str(value) for value in languages if str(value).strip()],
        gender=str(item["gender"]) if item.get("gender") else None,
        accent=str(item["accent"]) if item.get("accent") else None,
        styles=[str(value) for value in item.get("styles", []) if str(value).strip()] if isinstance(item.get("styles"), list) else [],
        preview_url=str(item["preview_url"]) if item.get("preview_url") else None,
        provider_metadata=dict(item.get("provider_metadata", {})) if isinstance(item.get("provider_metadata"), dict) else {},
    )


@router.get("", response_model=list[AIProviderRead])
def list_providers(session: Session = Depends(get_session)):
    return [_read(item) for item in session.exec(
        select(AIProvider).order_by(AIProvider.capability, AIProvider.id)
    ).all()]


@router.get("/catalog", response_model=list[ProviderCatalogItemRead])
def list_provider_catalog():
    return catalog_payload()


@router.post("/test", response_model=ProviderTestResponse)
def test_provider_draft(payload: ProviderTestRequest):
    if not payload.capability or not payload.provider_type:
        raise HTTPException(
            status_code=422,
            detail="capability and provider_type are required when testing an unsaved provider.",
        )
    provider = _make_provider(
        name=payload.name or "Draft provider",
        capability=payload.capability,
        provider_type=payload.provider_type,
        base_url=payload.base_url,
        api_key=payload.api_key,
        model_name=payload.model_name,
        is_enabled=True,
        is_default=False,
        extra_config=payload.extra_config,
        enabled_capabilities=payload.enabled_capabilities,
        enabled_formats=payload.enabled_formats,
    )
    return _test_provider(provider, payload.test_mode)


@router.post("", response_model=AIProviderRead, status_code=201)
def create_ai_provider(payload: AIProviderCreate, session: Session = Depends(get_session)):
    provider = _make_provider(
        name=payload.name,
        capability=payload.capability,
        provider_type=payload.provider_type,
        base_url=payload.base_url,
        api_key=payload.api_key,
        model_name=payload.model_name,
        is_enabled=payload.is_enabled,
        is_default=payload.is_default,
        extra_config=payload.extra_config,
        enabled_capabilities=payload.enabled_capabilities,
        enabled_formats=payload.enabled_formats,
    )
    if provider.is_default:
        _clear_other_defaults(session, provider.capability)
    session.add(provider)
    session.commit()
    session.refresh(provider)
    _reconcile_asr_scenes(session, provider.capability)
    return _read(provider)


@router.patch("/{provider_id}", response_model=AIProviderRead)
def update_ai_provider(provider_id: int, payload: AIProviderUpdate, session: Session = Depends(get_session)):
    provider = session.get(AIProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    if _descriptor_or_none(provider) is None:
        raise HTTPException(status_code=409, detail="Deprecated provider records can only be viewed or deleted.")
    candidate = _candidate_for_update(provider, payload)
    # Disabling a default must not leave an invisible disabled default record.
    if not candidate.is_enabled:
        candidate.is_default = False
    if candidate.is_default:
        _clear_other_defaults(session, candidate.capability, provider.id)
    for field in ("name", "provider_type", "base_url", "api_key", "model_name", "is_enabled", "is_default", "extra_config", "enabled_capabilities", "enabled_formats"):
        setattr(provider, field, getattr(candidate, field))
    provider.updated_at = datetime.now(UTC)
    session.add(provider)
    session.commit()
    session.refresh(provider)
    _reconcile_asr_scenes(session, provider.capability)
    return _read(provider)


@router.delete("/{provider_id}", status_code=204)
def delete_ai_provider(provider_id: int, session: Session = Depends(get_session)):
    provider = session.get(AIProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    capability = provider.capability
    session.delete(provider)
    session.commit()
    _reconcile_asr_scenes(session, capability)


@router.get("/{provider_id}/voices", response_model=list[ProviderVoiceRead])
def list_provider_voices(provider_id: int, session: Session = Depends(get_session)):
    provider = session.get(AIProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    if provider.capability != "tts":
        raise HTTPException(status_code=422, detail="Voice listing is only available for TTS providers.")
    descriptor = get_provider_descriptor(provider.capability, provider.provider_type)
    if ProviderCapability.LIST_VOICES not in descriptor.capabilities:
        raise HTTPException(
            status_code=409,
            detail="This TTS adapter does not support a live voice list; use its preset or a voice ID.",
        )
    try:
        voices = create_provider(provider).list_voices()
        return [_voice_response(item) for item in voices if isinstance(item, Mapping)]
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not list provider voices: {redact_provider_error(exc, provider.api_key)}",
        ) from exc


@router.post("/{provider_id}/test", response_model=ProviderTestResponse)
def test_ai_provider(
    provider_id: int,
    payload: ProviderTestRequest,
    session: Session = Depends(get_session),
):
    saved = session.get(AIProvider, provider_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Provider not found.")
    if _descriptor_or_none(saved) is None:
        raise HTTPException(status_code=409, detail="Deprecated provider records cannot be tested.")
    # Reuse draft construction so endpoint/model/key overrides are never
    # flushed into the session or persisted by a connection test.
    provider = _make_provider(
        name=payload.name or saved.name,
        capability=payload.capability or saved.capability,
        provider_type=payload.provider_type or saved.provider_type,
        base_url=payload.base_url if payload.base_url is not None else saved.base_url,
        api_key=payload.api_key if payload.api_key and payload.api_key.strip() else saved.api_key,
        model_name=payload.model_name if payload.model_name is not None else saved.model_name,
        is_enabled=True,
        is_default=False,
        extra_config=payload.extra_config if payload.extra_config is not None else (
            public_extra_config(
                get_provider_descriptor(saved.capability, saved.provider_type),
                parse_extra_config(saved.extra_config),
            )
        ),
        enabled_capabilities=payload.enabled_capabilities if payload.enabled_capabilities is not None else parse_string_list(saved.enabled_capabilities),
        enabled_formats=payload.enabled_formats if payload.enabled_formats is not None else parse_string_list(saved.enabled_formats),
    )
    return _test_provider(provider, payload.test_mode)


@router.get("/local-asr/status", response_model=LocalASRStatusRead)
def get_local_asr_status():
    return LocalASRStatusRead(**get_local_whisper_status().to_payload())


@router.post("/local-asr/test", response_model=LocalASRStatusRead)
def test_local_asr(payload: LocalASRTestRequest):
    if payload.load_model:
        load_local_whisper_model()
    return LocalASRStatusRead(**get_local_whisper_status().to_payload())


@router.post("/local-asr/release", response_model=LocalASRStatusRead)
def release_local_asr():
    return LocalASRStatusRead(**release_local_whisper_model().to_payload())


@router.get("/asr-scenes/settings", response_model=ASRSceneSettingRead)
def get_asr_scene_settings(session: Session = Depends(get_session)):
    return _scene_read(session)


@router.patch("/asr-scenes/settings", response_model=ASRSceneSettingRead)
def update_asr_scene_settings(payload: ASRSceneSettingUpdate, session: Session = Depends(get_session)):
    value = get_or_create_scene_settings(session)
    if payload.material_transcription_use_local is not None:
        value.material_transcription_use_local = payload.material_transcription_use_local
    if payload.recording_evaluation_use_local is not None:
        value.recording_evaluation_use_local = payload.recording_evaluation_use_local
    enforce_scene_capabilities(session, value)
    value.updated_at = datetime.now(UTC)
    session.add(value)
    session.commit()
    session.refresh(value)
    return _scene_read(session)
