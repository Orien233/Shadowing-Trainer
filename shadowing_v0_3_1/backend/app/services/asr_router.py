from dataclasses import dataclass

from sqlmodel import Session

from app.core.database import engine
from app.models.asr_scene_setting import ASRSceneSetting
from app.services.ai.asr import LocalWhisperASRProvider
from app.services.ai.audio_types import ProviderCapability
from app.services.provider_factory import (
    ProviderConfigurationError,
    get_declared_capabilities,
    get_provider,
    get_provider_record,
)

MATERIAL_TRANSCRIPTION = "material_transcription"
RECORDING_EVALUATION = "recording_evaluation"

_SCENE_REQUIREMENTS = {
    MATERIAL_TRANSCRIPTION: {
        ProviderCapability.TRANSCRIBE,
        ProviderCapability.WORD_TIMESTAMPS,
    },
    RECORDING_EVALUATION: {ProviderCapability.TRANSCRIBE},
}


@dataclass(frozen=True)
class ASRSceneAvailability:
    scene: str
    remote_available: bool
    missing_capabilities: tuple[str, ...]


def get_or_create_scene_settings(session: Session) -> ASRSceneSetting:
    settings = session.get(ASRSceneSetting, 1)
    if not settings:
        settings = ASRSceneSetting(id=1)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def get_scene_availability(session: Session, scene: str) -> ASRSceneAvailability:
    required = _SCENE_REQUIREMENTS.get(scene)
    if required is None:
        raise ValueError(f"Unknown ASR scene: {scene}")
    try:
        provider = get_provider_record(session, "asr")
    except ProviderConfigurationError:
        return ASRSceneAvailability(scene, False, ("remote_asr_provider",))
    missing = required - get_declared_capabilities(provider)
    return ASRSceneAvailability(
        scene,
        not missing,
        tuple(sorted(item.value for item in missing)),
    )


def enforce_scene_capabilities(session: Session, value: ASRSceneSetting | None = None) -> ASRSceneSetting:
    value = value or get_or_create_scene_settings(session)
    changed = False
    material = get_scene_availability(session, MATERIAL_TRANSCRIPTION)
    recording = get_scene_availability(session, RECORDING_EVALUATION)
    if not material.remote_available and not value.material_transcription_use_local:
        value.material_transcription_use_local = True
        changed = True
    if not recording.remote_available and not value.recording_evaluation_use_local:
        value.recording_evaluation_use_local = True
        changed = True
    if changed:
        session.add(value)
        session.commit()
        session.refresh(value)
    return value


def require_remote_scene_available(session: Session, scene: str) -> None:
    availability = get_scene_availability(session, scene)
    if not availability.remote_available:
        missing = ", ".join(availability.missing_capabilities)
        raise ProviderConfigurationError(
            f"Remote ASR cannot be used for {scene}; missing: {missing}."
        )


def get_asr_provider(session: Session, scene: str):
    scene_settings = enforce_scene_capabilities(session)
    local = (
        scene_settings.material_transcription_use_local
        if scene == MATERIAL_TRANSCRIPTION
        else scene_settings.recording_evaluation_use_local
        if scene == RECORDING_EVALUATION
        else None
    )
    if local is None:
        raise ValueError(f"Unknown ASR scene: {scene}")
    if local:
        return LocalWhisperASRProvider()
    require_remote_scene_available(session, scene)
    return get_provider(session, "asr")


def transcribe_for_scene(scene: str, audio_path: str, *, word_timestamps: bool = False) -> list[dict]:
    with Session(engine) as session:
        result = get_asr_provider(session, scene).transcribe(audio_path, word_timestamps=word_timestamps)
        return result.as_legacy_segments()


def transcribe_text_for_scene(scene: str, audio_path: str) -> str:
    with Session(engine) as session:
        return get_asr_provider(session, scene).transcribe_text(audio_path)
