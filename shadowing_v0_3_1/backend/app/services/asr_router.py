from datetime import UTC, datetime

from sqlmodel import Session

from app.core.database import engine
from app.models.asr_scene_setting import ASRSceneSetting
from app.services.ai.asr import LocalWhisperASRProvider
from app.services.provider_factory import ProviderConfigurationError, get_provider

MATERIAL_TRANSCRIPTION = "material_transcription"
RECORDING_EVALUATION = "recording_evaluation"


def get_or_create_scene_settings(session: Session) -> ASRSceneSetting:
    settings = session.get(ASRSceneSetting, 1)
    if not settings:
        settings = ASRSceneSetting(id=1)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def get_asr_provider(session: Session, scene: str):
    scene_settings = get_or_create_scene_settings(session)
    local = scene_settings.material_transcription_use_local if scene == MATERIAL_TRANSCRIPTION else scene_settings.recording_evaluation_use_local if scene == RECORDING_EVALUATION else None
    if local is None:
        raise ValueError(f"Unknown ASR scene: {scene}")
    if local:
        return LocalWhisperASRProvider()
    try:
        return get_provider(session, "asr")
    except ProviderConfigurationError as exc:
        raise ProviderConfigurationError(f"{scene} is configured for remote ASR, but no default enabled remote ASR provider exists.") from exc


def transcribe_for_scene(scene: str, audio_path: str, *, word_timestamps: bool = False) -> list[dict]:
    with Session(engine) as session:
        return get_asr_provider(session, scene).transcribe(audio_path, word_timestamps=word_timestamps)


def transcribe_text_for_scene(scene: str, audio_path: str) -> str:
    with Session(engine) as session:
        return get_asr_provider(session, scene).transcribe_text(audio_path)
