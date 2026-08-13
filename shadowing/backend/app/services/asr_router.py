from dataclasses import dataclass

from sqlmodel import Session

from app.core.database import engine
from app.models.asr_scene_setting import ASRSceneSetting
from app.services.ai.asr.base import UnsupportedASRLanguageError
from app.services.ai.asr.local_whisper import LocalWhisperASRProvider
from app.services.ai.audio_types import ProviderCapability
from app.services.local_whisper_runtime import get_local_whisper_status
from app.services.provider_factory import (
    ProviderConfigurationError,
    get_enabled_capabilities,
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
    remote_unavailable_reason: str | None
    local_available: bool
    local_unavailable_reason: str | None


def _requested_local(value: ASRSceneSetting, scene: str) -> bool:
    if scene == MATERIAL_TRANSCRIPTION:
        return value.material_transcription_use_local
    if scene == RECORDING_EVALUATION:
        return value.recording_evaluation_use_local
    raise ValueError(f"Unknown ASR scene: {scene}")


def get_or_create_scene_settings(session: Session) -> ASRSceneSetting:
    """Return the persisted settings, creating the one settings row on writes.

    Read APIs must use :func:`get_scene_settings_for_read` instead.  Keeping
    this write explicitly named avoids a seemingly harmless GET request
    changing a user's database.
    """
    settings = session.get(ASRSceneSetting, 1)
    if not settings:
        settings = ASRSceneSetting(id=1)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def get_scene_settings_for_read(session: Session) -> ASRSceneSetting:
    """Return saved settings or the default values without persisting them."""
    return session.get(ASRSceneSetting, 1) or ASRSceneSetting(id=1)


def get_scene_availability(
    session: Session,
    scene: str,
    *,
    language: str | None = None,
) -> ASRSceneAvailability:
    required = _SCENE_REQUIREMENTS.get(scene)
    if required is None:
        raise ValueError(f"Unknown ASR scene: {scene}")
    try:
        provider = get_provider_record(session, "asr")
    except ProviderConfigurationError:
        local = get_local_whisper_status()
        return ASRSceneAvailability(
            scene,
            False,
            ("remote_asr_provider",),
            None,
            local.runtime_ready,
            local.error,
        )
    missing = required - get_enabled_capabilities(provider)
    remote_unavailable_reason: str | None = None
    if not missing and language is not None and str(language).strip():
        remote_provider = get_provider(session, "asr", provider.id)
        try:
            remote_provider.provider_language(language)
        except UnsupportedASRLanguageError as exc:
            remote_unavailable_reason = str(exc)
    local = get_local_whisper_status()
    return ASRSceneAvailability(
        scene,
        not missing and remote_unavailable_reason is None,
        tuple(sorted(item.value for item in missing)),
        remote_unavailable_reason,
        local.runtime_ready,
        local.error,
    )


def resolve_scene_route(
    session: Session,
    scene: str,
    value: ASRSceneSetting | None = None,
    *,
    language: str | None = None,
) -> str:
    """Return ``local``, ``remote``, or ``unavailable`` for a scene.

    The persisted boolean is the user's preferred route.  A usable alternate
    route is selected only when that preference cannot run, so remote-only
    installs work without a hidden Whisper dependency and offline installs
    still fall back safely to local ASR.
    """
    value = value or get_scene_settings_for_read(session)
    availability = get_scene_availability(session, scene, language=language)
    if _requested_local(value, scene):
        if availability.local_available:
            return "local"
        if availability.remote_available:
            return "remote"
    else:
        if availability.remote_available:
            return "remote"
        if availability.local_available:
            return "local"
    return "unavailable"


def enforce_scene_capabilities(session: Session, value: ASRSceneSetting | None = None) -> ASRSceneSetting:
    """Persist a viable route when exactly one route is available.

    When both routes are usable, user preference is retained.  When neither is
    usable, it is intentionally retained too; the read API exposes the scene
    as unavailable rather than pretending a fallback exists.
    """
    value = value or get_or_create_scene_settings(session)
    changed = False
    for scene, field in (
        (MATERIAL_TRANSCRIPTION, "material_transcription_use_local"),
        (RECORDING_EVALUATION, "recording_evaluation_use_local"),
    ):
        availability = get_scene_availability(session, scene)
        desired_local = getattr(value, field)
        if desired_local and not availability.local_available and availability.remote_available:
            setattr(value, field, False)
            changed = True
        elif not desired_local and not availability.remote_available and availability.local_available:
            setattr(value, field, True)
            changed = True
    if changed:
        session.add(value)
        session.commit()
        session.refresh(value)
    return value


def effective_scene_flags(session: Session, value: ASRSceneSetting | None = None) -> tuple[bool, bool]:
    """Calculate safe scene routing without mutating the settings row.

    A disabled remote capability always wins over a previously persisted
    ``False`` toggle.  This makes direct database/API bypasses safe and lets
    a GET accurately show the forced-local state without causing a write.
    """
    value = value or get_scene_settings_for_read(session)
    return (
        resolve_scene_route(session, MATERIAL_TRANSCRIPTION, value) == "local",
        resolve_scene_route(session, RECORDING_EVALUATION, value) == "local",
    )


def require_remote_scene_available(
    session: Session,
    scene: str,
    *,
    language: str | None = None,
) -> None:
    availability = get_scene_availability(session, scene, language=language)
    if not availability.remote_available:
        if availability.remote_unavailable_reason:
            raise ProviderConfigurationError(
                f"Remote ASR cannot be used for {scene}: "
                f"{availability.remote_unavailable_reason}"
            )
        missing = ", ".join(availability.missing_capabilities)
        raise ProviderConfigurationError(
            f"Remote ASR cannot be used for {scene}; missing: {missing}."
        )


def get_asr_provider(session: Session, scene: str, *, language: str | None = None):
    route = resolve_scene_route(session, scene, language=language)
    if route == "local":
        return LocalWhisperASRProvider()
    if route == "remote":
        require_remote_scene_available(session, scene, language=language)
        return get_provider(session, "asr")
    availability = get_scene_availability(session, scene, language=language)
    remote_reason = availability.remote_unavailable_reason or ", ".join(availability.missing_capabilities) or "not configured"
    local_reason = availability.local_unavailable_reason or "not available"
    raise ProviderConfigurationError(
        f"No ASR route is available for {scene}. Local Whisper: {local_reason}. "
        f"Remote ASR: {remote_reason}."
    )


def transcribe_for_scene(
    scene: str,
    audio_path: str,
    *,
    word_timestamps: bool = False,
    language: str | None = None,
) -> list[dict]:
    with Session(engine) as session:
        result = get_asr_provider(session, scene, language=language).transcribe(
            audio_path,
            word_timestamps=word_timestamps,
            language=language,
        )
        return result.as_legacy_segments()


def transcribe_text_for_scene(
    scene: str,
    audio_path: str,
    *,
    language: str | None = None,
) -> str:
    with Session(engine) as session:
        return get_asr_provider(session, scene, language=language).transcribe_text(audio_path, language=language)
