from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.ai_provider import AIProvider
from app.models.asr_scene_setting import ASRSceneSetting
from app.models.job import Job
from app.models.material import Material
from app.models.sentence import Sentence
from app.models.text_practice import TextPractice, TextPracticeWord
from app.models.word_collection import WordCollection
from app.schemas.text_practice import TextGenerationRequest
from app.services import asr_router, text_generation_service, tts_service
from app.services.ai.asr.local_whisper import LocalWhisperASRProvider
from app.services.ai.audio_types import TTSResult
from app.services.provider_factory import create_provider
from app.api.providers import _read


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=[AIProvider.__table__, ASRSceneSetting.__table__, TextPractice.__table__, TextPracticeWord.__table__, WordCollection.__table__, Job.__table__, Material.__table__, Sentence.__table__])
    return engine


def test_factory_creates_openai_compatible_provider():
    llm = create_provider(AIProvider(name="x", capability="llm", provider_type="openai_compatible", base_url="https://example.test/v1", api_key="secret", model_name="model"))
    tts = create_provider(AIProvider(name="x", capability="tts", provider_type="openai_compatible", base_url="https://example.test/v1", api_key="secret", model_name="model"))
    asr = create_provider(AIProvider(name="x", capability="asr", provider_type="openai_compatible", base_url="https://example.test/v1", api_key="secret", model_name="model"))
    assert llm.__class__.__name__ == "OpenAICompatibleLLMProvider"
    assert tts.__class__.__name__ == "OpenAICompatibleTTSProvider"
    assert asr.__class__.__name__ == "OpenAICompatibleRemoteASRProvider"


def test_factory_creates_azure_audio_adapters():
    tts = create_provider(AIProvider(name="azure", capability="tts", provider_type="azure_speech", base_url="https://westus.tts.speech.microsoft.com", api_key="secret", model_name="en-US-AvaMultilingualNeural"))
    asr = create_provider(AIProvider(name="azure", capability="asr", provider_type="azure_speech", base_url="https://westus.stt.speech.microsoft.com", api_key="secret", model_name="conversation"))
    assert tts.__class__.__name__ == "AzureSpeechTTSProvider"
    assert asr.__class__.__name__ == "AzureSpeechASRProvider"


def test_provider_read_masks_api_key():
    response = _read(AIProvider(id=3, name="secret", capability="llm", provider_type="openai_compatible", api_key="sk-very-secret-key", model_name="model"))
    assert response.api_key_masked is not None
    assert "very-secret" not in response.api_key_masked
    assert "sk-very-secret-key" not in response.model_dump_json()


def test_asr_router_honours_independent_scene_switches(monkeypatch):
    engine = _engine()
    remote = object()
    monkeypatch.setattr(asr_router, "get_provider", lambda *_args, **_kwargs: remote)
    with Session(engine) as session:
        setting = ASRSceneSetting(material_transcription_use_local=True, recording_evaluation_use_local=False)
        session.add(setting); session.commit()
        assert isinstance(asr_router.get_asr_provider(session, asr_router.MATERIAL_TRANSCRIPTION), LocalWhisperASRProvider)
        assert asr_router.get_asr_provider(session, asr_router.RECORDING_EVALUATION) is remote


def test_generated_word_selection_and_invalid_json_fallback(monkeypatch):
    engine = _engine()
    class Provider:
        def generate_json(self, **_kwargs): raise ValueError("bad json")
        def generate_text(self, **_kwargs): return "```json\n{\"title\": \"Trip\", \"body\": \"I travel with apple.\", \"used_words\": [\"apple\"], \"unused_words\": [\"book\"]}\n```"
    monkeypatch.setattr(text_generation_service, "get_provider_record", lambda *_args: AIProvider(id=7, name="fake", capability="llm", provider_type="openai_compatible", base_url="x", model_name="x"))
    monkeypatch.setattr(text_generation_service, "get_provider", lambda *_args: Provider())
    with Session(engine) as session:
        first = WordCollection(material_id=1, sentence_id=1, word_text="apple", normalized_word="apple")
        second = WordCollection(material_id=1, sentence_id=1, word_text="book", normalized_word="book")
        session.add(first); session.add(second); session.commit()
        practice = text_generation_service.create_generated_practice(session, TextGenerationRequest(word_selection="manual", word_collection_ids=[first.id, second.id], target_language="en", difficulty="beginner", desired_length=80))
        assert practice.title == "Trip"
        assert text_generation_service.json_words(practice.used_words_json) == ["apple"]
        assert text_generation_service.json_words(practice.unused_words_json) == ["book"]


def test_tts_job_creates_material_and_sentences(monkeypatch, tmp_path: Path):
    engine = _engine()
    old_engine, old_data_dir = tts_service.engine, tts_service.settings.data_dir
    monkeypatch.setattr(tts_service, "engine", engine)
    tts_service.settings.data_dir = str(tmp_path)
    class Provider:
        def synthesize(self, _request): return TTSResult(audio=b"audio")
    monkeypatch.setattr(tts_service, "get_provider", lambda *_args: Provider())
    monkeypatch.setattr(tts_service, "_merge_audio", lambda _parts, target: target.write_bytes(b"merged"))
    monkeypatch.setattr(tts_service, "get_audio_duration", lambda path: 1.25 if path.name != "text_practice_1.mp3" else 2.5)
    try:
        with Session(engine) as session:
            practice = TextPractice(title="Generated", body="First sentence. Second sentence!", source_type="import", tts_provider_id=1, tts_options_json='{"speed_preset":"normal"}')
            session.add(practice); session.commit()
        result = tts_service.run_tts_synthesis("job", {"text_practice_id": 1})
        assert result["material_id"] == 1
        with Session(engine) as session:
            assert len(session.exec(select(Sentence).where(Sentence.material_id == 1)).all()) == 2
            assert session.get(Material, 1).status == "ready"
    finally:
        tts_service.settings.data_dir = old_data_dir
        monkeypatch.setattr(tts_service, "engine", old_engine)
