import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.ai_provider import AIProvider
from app.schemas.ai_provider import AIProviderCreate, AIProviderRead, AIProviderUpdate, ASRSceneSettingRead, ASRSceneSettingUpdate, ProviderTestRequest, ProviderTestResponse
from app.services.asr_router import (
    MATERIAL_TRANSCRIPTION,
    RECORDING_EVALUATION,
    enforce_scene_capabilities,
    get_or_create_scene_settings,
    get_scene_availability,
)
from app.services.provider_factory import create_provider, get_declared_capabilities, parse_extra_config

router = APIRouter(prefix="/api/providers", tags=["providers"])


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 4:
        return "*" * len(key)
    return f"{key[:2]}{'*' * max(4, len(key) - 6)}{key[-4:]}"


def _read(provider: AIProvider) -> AIProviderRead:
    return AIProviderRead(id=provider.id, name=provider.name, capability=provider.capability, provider_type=provider.provider_type, base_url=provider.base_url, api_key_masked=_mask_key(provider.api_key), model_name=provider.model_name, is_enabled=provider.is_enabled, is_default=provider.is_default, extra_config=parse_extra_config(provider.extra_config), capabilities=sorted(item.value for item in get_declared_capabilities(provider)), created_at=provider.created_at, updated_at=provider.updated_at)


def _scene_read(session: Session) -> ASRSceneSettingRead:
    value = enforce_scene_capabilities(session, get_or_create_scene_settings(session))
    material = get_scene_availability(session, MATERIAL_TRANSCRIPTION)
    recording = get_scene_availability(session, RECORDING_EVALUATION)
    return ASRSceneSettingRead(
        material_transcription_use_local=value.material_transcription_use_local,
        recording_evaluation_use_local=value.recording_evaluation_use_local,
        updated_at=value.updated_at,
        material_transcription_remote_available=material.remote_available,
        material_transcription_missing_capabilities=list(material.missing_capabilities),
        recording_evaluation_remote_available=recording.remote_available,
        recording_evaluation_missing_capabilities=list(recording.missing_capabilities),
    )


def _clear_other_defaults(session: Session, capability: str, current_id: int | None = None) -> None:
    for provider in session.exec(select(AIProvider).where(AIProvider.capability == capability, AIProvider.is_default == True)).all():  # noqa: E712
        if provider.id != current_id:
            provider.is_default = False
            session.add(provider)


@router.get("", response_model=list[AIProviderRead])
def list_providers(session: Session = Depends(get_session)):
    return [_read(item) for item in session.exec(select(AIProvider).order_by(AIProvider.capability, AIProvider.id)).all()]


@router.post("", response_model=AIProviderRead, status_code=201)
def create_ai_provider(payload: AIProviderCreate, session: Session = Depends(get_session)):
    if payload.is_default:
        _clear_other_defaults(session, payload.capability)
    provider = AIProvider(name=payload.name.strip(), capability=payload.capability, provider_type=payload.provider_type.strip(), base_url=payload.base_url.strip() if payload.base_url else None, api_key=payload.api_key.strip() if payload.api_key else None, model_name=payload.model_name.strip() if payload.model_name else None, is_enabled=payload.is_enabled, is_default=payload.is_default, extra_config=json.dumps(payload.extra_config, ensure_ascii=False))
    session.add(provider); session.commit(); session.refresh(provider)
    return _read(provider)


@router.patch("/{provider_id}", response_model=AIProviderRead)
def update_ai_provider(provider_id: int, payload: AIProviderUpdate, session: Session = Depends(get_session)):
    provider = session.get(AIProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_default"):
        _clear_other_defaults(session, provider.capability, provider.id)
    for field in ("name", "provider_type", "base_url", "model_name", "is_enabled", "is_default"):
        if field in changes:
            value = changes[field]
            setattr(provider, field, value.strip() if isinstance(value, str) else value)
    # An omitted or blank key means retain the key already stored by the backend.
    if changes.get("api_key"):
        provider.api_key = changes["api_key"].strip()
    if "extra_config" in changes:
        provider.extra_config = json.dumps(changes["extra_config"] or {}, ensure_ascii=False)
    provider.updated_at = datetime.now(UTC)
    session.add(provider); session.commit(); session.refresh(provider)
    return _read(provider)


@router.delete("/{provider_id}", status_code=204)
def delete_ai_provider(provider_id: int, session: Session = Depends(get_session)):
    provider = session.get(AIProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    session.delete(provider); session.commit()


@router.post("/{provider_id}/test", response_model=ProviderTestResponse)
def test_ai_provider(provider_id: int, payload: ProviderTestRequest, session: Session = Depends(get_session)):
    provider = session.get(AIProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    if payload.base_url is not None:
        provider.base_url = payload.base_url
    if payload.model_name is not None:
        provider.model_name = payload.model_name
    if payload.api_key:
        provider.api_key = payload.api_key
    try:
        message = create_provider(provider).test_connection()
        return ProviderTestResponse(ok=True, message=message, capabilities=sorted(item.value for item in get_declared_capabilities(provider)))
    except Exception as exc:
        # Avoid exposing URLs with query credentials, headers, or API key content.
        return ProviderTestResponse(ok=False, message=f"Connection test failed: {type(exc).__name__}: {str(exc).replace(provider.api_key or '', '[redacted]')[:400]}", capabilities=sorted(item.value for item in get_declared_capabilities(provider)))


@router.get("/asr-scenes/settings", response_model=ASRSceneSettingRead)
def get_asr_scene_settings(session: Session = Depends(get_session)):
    return _scene_read(session)


@router.patch("/asr-scenes/settings", response_model=ASRSceneSettingRead)
def update_asr_scene_settings(payload: ASRSceneSettingUpdate, session: Session = Depends(get_session)):
    value = enforce_scene_capabilities(session, get_or_create_scene_settings(session))
    if payload.material_transcription_use_local is not None:
        if not payload.material_transcription_use_local:
            availability = get_scene_availability(session, MATERIAL_TRANSCRIPTION)
            if not availability.remote_available:
                raise HTTPException(status_code=409, detail=f"Remote material transcription is unavailable: {', '.join(availability.missing_capabilities)}.")
        value.material_transcription_use_local = payload.material_transcription_use_local
    if payload.recording_evaluation_use_local is not None:
        if not payload.recording_evaluation_use_local:
            availability = get_scene_availability(session, RECORDING_EVALUATION)
            if not availability.remote_available:
                raise HTTPException(status_code=409, detail=f"Remote recording evaluation is unavailable: {', '.join(availability.missing_capabilities)}.")
        value.recording_evaluation_use_local = payload.recording_evaluation_use_local
    value.updated_at = datetime.now(UTC)
    session.add(value); session.commit(); session.refresh(value)
    return _scene_read(session)
