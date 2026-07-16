from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
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
from app.schemas.ai_provider import ASRSceneSettingUpdate, ProviderTestRequest
from app.schemas.text_practice import TextGenerationRequest
from app.services import asr_router, text_generation_service, tts_service
from app.services.ai.asr.local_whisper import LocalWhisperASRProvider
from app.services.ai.audio_types import ProviderCapability, TTSResult
from app.services.ai.tts.base import TTSRequest
from app.services.ai.tts.openai_compatible import OpenAICompatibleTTSProvider
from app.services.ai.tts.mimo import MiMoTTSProvider
from app.services.ai.asr.mimo import MiMoASRProvider
from app.services.provider_factory import create_provider, get_declared_capabilities
from app.api import providers as providers_api
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


def test_factory_creates_mimo_audio_adapters():
    tts = create_provider(AIProvider(name="mimo", capability="tts", provider_type="mimo_tts", base_url="https://api.xiaomimimo.com/v1/chat/completions", api_key="secret", model_name="mimo-v2.5-tts"))
    asr = create_provider(AIProvider(name="mimo", capability="asr", provider_type="mimo_asr", base_url="https://api.xiaomimimo.com/v1/chat/completions", api_key="secret", model_name="mimo-v2.5-asr"))
    assert tts.__class__.__name__ == "MiMoTTSProvider"
    assert asr.__class__.__name__ == "MiMoASRProvider"


def test_adapter_capabilities_are_static_and_safe_to_read():
    llm = AIProvider(name="llm", capability="llm", provider_type="openai_compatible", base_url="https://example.test/v1", model_name="model")
    remote_asr = AIProvider(name="remote", capability="asr", provider_type="openai_compatible", base_url="https://example.test/v1", model_name="model")
    azure_asr = AIProvider(name="azure", capability="asr", provider_type="azure_speech", base_url="https://example.test", model_name="model")
    mimo_asr = AIProvider(name="mimo", capability="asr", provider_type="mimo_asr", base_url="https://example.test", model_name="model")
    assert get_declared_capabilities(llm) == {ProviderCapability.GENERATE_TEXT, ProviderCapability.GENERATE_JSON}
    assert get_declared_capabilities(remote_asr) == {ProviderCapability.TRANSCRIBE, ProviderCapability.WORD_TIMESTAMPS}
    assert get_declared_capabilities(azure_asr) == {ProviderCapability.TRANSCRIBE}
    assert get_declared_capabilities(mimo_asr) == {ProviderCapability.TRANSCRIBE}


def test_openai_tts_uses_user_provided_full_endpoint(monkeypatch):
    called: dict[str, object] = {}
    class Response:
        content = b"audio"
        headers: dict[str, str] = {}
        def raise_for_status(self): pass
    def fake_post(url, **kwargs):
        called["url"] = url
        return Response()
    monkeypatch.setattr("app.services.ai.tts.openai_compatible.httpx.post", fake_post)
    provider = OpenAICompatibleTTSProvider(base_url="https://voice.example/custom/speech", api_key="key", model_name="model")
    provider.synthesize(TTSRequest(text="Hello"))
    assert called["url"] == "https://voice.example/custom/speech"


def test_mimo_tts_uses_chat_completion_schema_and_decodes_audio(monkeypatch):
    called: dict[str, object] = {}
    class Response:
        headers: dict[str, str] = {}
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"audio": {"data": base64.b64encode(b"wav-bytes").decode("ascii")}}}]}
    def fake_post(url, **kwargs):
        called["url"], called["payload"] = url, kwargs["json"]
        return Response()
    monkeypatch.setattr("app.services.ai.tts.mimo.httpx.post", fake_post)
    result = MiMoTTSProvider(base_url="https://api.xiaomimimo.com/v1/chat/completions", api_key="key", model_name="mimo-v2.5-tts").synthesize(TTSRequest(text="Hello", voice="Chloe"))
    assert called["url"] == "https://api.xiaomimimo.com/v1/chat/completions"
    assert called["payload"]["messages"][-1] == {"role": "assistant", "content": "Hello"}
    assert result.audio == b"wav-bytes" and result.extension == "wav"


def test_mimo_asr_uses_chat_completion_audio_part(monkeypatch, tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"wave")
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "hello world"}}]}
    monkeypatch.setattr("app.services.ai.asr.mimo.httpx.post", lambda *_args, **_kwargs: Response())
    result = MiMoASRProvider(base_url="https://api.xiaomimimo.com/v1/chat/completions", api_key="key", model_name="mimo-v2.5-asr").transcribe(str(audio))
    assert result.text == "hello world"


def test_provider_read_masks_api_key():
    response = _read(AIProvider(id=3, name="secret", capability="llm", provider_type="openai_compatible", api_key="sk-very-secret-key", model_name="model"))
    assert response.api_key_masked is not None
    assert "very-secret" not in response.api_key_masked
    assert "sk-very-secret-key" not in response.model_dump_json()
    assert response.capabilities == ["generate_json", "generate_text"]


def test_provider_test_response_reports_static_capabilities_without_leaking_key(monkeypatch):
    engine = _engine()
    class Provider:
        def test_connection(self):
            raise RuntimeError("request rejected for secret-value")
    monkeypatch.setattr(providers_api, "create_provider", lambda *_args: Provider())
    with Session(engine) as session:
        provider = AIProvider(name="private", capability="asr", provider_type="mimo_asr", base_url="https://example.test", api_key="secret-value", model_name="mimo")
        session.add(provider); session.commit(); session.refresh(provider)
        response = providers_api.test_ai_provider(provider.id, ProviderTestRequest(), session)
    assert response.ok is False
    assert response.capabilities == ["transcribe"]
    assert "secret-value" not in response.message


def test_asr_router_honours_independent_scene_switches(monkeypatch):
    engine = _engine()
    remote = object()
    monkeypatch.setattr(asr_router, "get_provider", lambda *_args, **_kwargs: remote)
    with Session(engine) as session:
        session.add(AIProvider(name="remote", capability="asr", provider_type="openai_compatible", base_url="https://example.test/v1", api_key="key", model_name="asr", is_default=True))
        setting = ASRSceneSetting(material_transcription_use_local=True, recording_evaluation_use_local=False)
        session.add(setting); session.commit()
        assert isinstance(asr_router.get_asr_provider(session, asr_router.MATERIAL_TRANSCRIPTION), LocalWhisperASRProvider)
        assert asr_router.get_asr_provider(session, asr_router.RECORDING_EVALUATION) is remote


def test_mimo_asr_locks_material_scene_but_allows_remote_recording():
    engine = _engine()
    with Session(engine) as session:
        session.add(AIProvider(name="mimo", capability="asr", provider_type="mimo_asr", base_url="https://example.test", api_key="key", model_name="mimo", is_default=True))
        session.add(ASRSceneSetting(material_transcription_use_local=False, recording_evaluation_use_local=False))
        session.commit()
        settings = providers_api.get_asr_scene_settings(session)
        assert settings.material_transcription_use_local is True
        assert settings.material_transcription_remote_available is False
        assert settings.material_transcription_missing_capabilities == ["word_timestamps"]
        assert settings.recording_evaluation_use_local is False
        assert settings.recording_evaluation_remote_available is True
        with pytest.raises(HTTPException) as exc:
            providers_api.update_asr_scene_settings(ASRSceneSettingUpdate(material_transcription_use_local=False), session)
        assert exc.value.status_code == 409


def test_word_timestamp_remote_asr_unlocks_both_scenes():
    engine = _engine()
    with Session(engine) as session:
        session.add(AIProvider(name="remote", capability="asr", provider_type="openai_compatible", base_url="https://example.test/v1", api_key="key", model_name="asr", is_default=True))
        session.add(ASRSceneSetting())
        session.commit()
        result = providers_api.update_asr_scene_settings(
            ASRSceneSettingUpdate(material_transcription_use_local=False, recording_evaluation_use_local=False),
            session,
        )
        assert result.material_transcription_remote_available is True
        assert result.recording_evaluation_remote_available is True
        assert result.material_transcription_use_local is False
        assert result.recording_evaluation_use_local is False


def test_generated_word_selection_and_invalid_json_fallback(monkeypatch):
    engine = _engine()
    class Provider:
        def generate_json(self, **_kwargs): raise ValueError("bad json")
        def generate_text(self, **_kwargs): return "```json\n{\"title\": \"Trip\", \"body\": \"I travel with apple.\", \"used_words\": [\"apple\"], \"unused_words\": [\"book\"]}\n```"
    record = AIProvider(id=7, name="fake", capability="llm", provider_type="openai_compatible", base_url="x", model_name="x")
    monkeypatch.setattr(text_generation_service, "require_provider_capabilities", lambda *_args, **_kwargs: record)
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
            provider = AIProvider(name="tts", capability="tts", provider_type="openai_compatible", base_url="https://example.test/audio/speech", api_key="key", model_name="tts")
            session.add(provider); session.commit(); session.refresh(provider)
            practice = TextPractice(title="Generated", body="First sentence. Second sentence!", source_type="import", tts_provider_id=provider.id, tts_options_json='{"speed_preset":"normal"}')
            session.add(practice); session.commit()
        result = tts_service.run_tts_synthesis("job", {"text_practice_id": 1})
        assert result["material_id"] == 1
        with Session(engine) as session:
            assert len(session.exec(select(Sentence).where(Sentence.material_id == 1)).all()) == 2
            assert session.get(Material, 1).status == "ready"
    finally:
        tts_service.settings.data_dir = old_data_dir
        monkeypatch.setattr(tts_service, "engine", old_engine)
