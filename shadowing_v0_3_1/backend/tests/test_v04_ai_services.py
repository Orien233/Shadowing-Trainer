from __future__ import annotations

import base64
import shutil
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
from app.services.ai.audio_types import ProviderCapability, RawPCMFormat, TTSResult
from app.services.ai.tts.base import TTSRequest
from app.services.ai.tts.openai_compatible import OpenAICompatibleTTSProvider
from app.services.ai.tts.mimo import MiMoTTSProvider
from app.services.ai.asr.mimo import MiMoASRProvider
from app.services.ai.asr.azure_speech import AzureSpeechASRProvider
from app.services.ai.adapter_registry import catalog_payload, get_adapter_descriptor
from app.services.ai.llm._shared import extract_json_object
from app.services.provider_security import redact_provider_error, sanitize_url
from app.services.provider_factory import ProviderConfigurationError, create_provider, get_declared_capabilities, get_enabled_capabilities, validate_provider_boundaries
from app.api import providers as providers_api
from app.api.providers import _read


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=[AIProvider.__table__, ASRSceneSetting.__table__, TextPractice.__table__, TextPracticeWord.__table__, WordCollection.__table__, Job.__table__, Material.__table__, Sentence.__table__])
    return engine


def test_factory_creates_openai_compatible_provider():
    llm = create_provider(AIProvider(name="x", capability="llm", provider_type="openai_compatible", base_url="https://example.test/v1", api_key="secret", model_name="model"))
    tts = create_provider(AIProvider(name="x", capability="tts", provider_type="openai_compatible", base_url="https://example.test/v1", api_key="secret", model_name="model"))
    asr = create_provider(AIProvider(name="x", capability="asr", provider_type="openai_audio_asr", base_url="https://example.test/v1", api_key="secret", model_name="model"))
    assert llm.__class__.__name__ == "OpenAICompatibleLLMProvider"
    assert tts.__class__.__name__ == "OpenAICompatibleTTSProvider"
    assert asr.__class__.__name__ == "OpenAIWhisperASRProvider"


def test_unsupported_adapter_cannot_be_created():
    with pytest.raises(ProviderConfigurationError):
        create_provider(AIProvider(name="azure", capability="tts", provider_type="azure_speech", base_url="https://example.test", api_key="secret", model_name="voice"))


def test_factory_creates_mimo_audio_adapters():
    tts = create_provider(AIProvider(name="mimo", capability="tts", provider_type="mimo_tts", base_url="https://api.xiaomimimo.com/v1/chat/completions", api_key="secret", model_name="mimo-v2.5-tts"))
    asr = create_provider(AIProvider(name="mimo", capability="asr", provider_type="mimo_asr", base_url="https://api.xiaomimimo.com/v1/chat/completions", api_key="secret", model_name="mimo-v2.5-asr"))
    assert tts.__class__.__name__ == "MiMoTTSProvider"
    assert asr.__class__.__name__ == "MiMoASRProvider"


def test_adapter_registry_resolves_legacy_aliases_and_exposes_safe_catalog():
    assert get_adapter_descriptor("llm", "openai_compatible").canonical_key == "openai_chat_compatible"
    assert get_adapter_descriptor("tts", "openai_compatible").canonical_key == "openai_audio_tts"
    assert get_adapter_descriptor("asr", "openai_compatible") is None
    catalog = catalog_payload()
    keys = {(item["kind"], item["key"]) for item in catalog}
    assert keys == {("llm", "openai_chat_compatible"), ("tts", "openai_audio_tts"), ("tts", "mimo_tts"), ("asr", "openai_audio_asr"), ("asr", "mimo_asr")}
    assert all("api_key" not in {field["key"] for field in item["config_fields"]} for item in catalog)


def test_legacy_profiles_are_not_registered():
    assert get_adapter_descriptor("llm", "ollama_chat") is None


def test_adapter_capabilities_are_static_and_safe_to_read():
    llm = AIProvider(name="llm", capability="llm", provider_type="openai_compatible", base_url="https://example.test/v1", model_name="model")
    remote_asr = AIProvider(name="remote", capability="asr", provider_type="openai_audio_asr", base_url="https://example.test/v1", model_name="model")
    mimo_asr = AIProvider(name="mimo", capability="asr", provider_type="mimo_asr", base_url="https://example.test", model_name="model")
    assert get_declared_capabilities(llm) == {ProviderCapability.GENERATE_TEXT, ProviderCapability.GENERATE_JSON}
    assert get_declared_capabilities(remote_asr) == {ProviderCapability.TRANSCRIBE, ProviderCapability.WORD_TIMESTAMPS}
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
    monkeypatch.setattr("app.services.ai.tts.openai_compatible.provider_http.post", fake_post)
    provider = OpenAICompatibleTTSProvider(base_url="https://voice.example/custom/speech", api_key="key", model_name="model")
    provider.synthesize(TTSRequest(text="Hello"))
    assert called["url"] == "https://voice.example/custom/speech"


def test_openai_pcm_result_declares_the_decoding_contract(monkeypatch):
    class Response:
        content = b"raw-pcm"
        headers: dict[str, str] = {}
        def raise_for_status(self): pass
    monkeypatch.setattr("app.services.ai.tts.openai_compatible.provider_http.post", lambda *_args, **_kwargs: Response())
    result = OpenAICompatibleTTSProvider(
        base_url="https://voice.example/custom/speech",
        api_key="key",
        model_name="tts",
        extra_config={"response_format": "pcm"},
    ).synthesize(TTSRequest(text="Hello"))
    assert result.raw_pcm == RawPCMFormat(sample_rate=24000, channels=1, sample_format="s16le")


def test_mimo_pcm_requires_explicit_sample_rate_before_request(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai.tts.mimo.provider_http.post",
        lambda *_args, **_kwargs: pytest.fail("invalid PCM config must fail before a billable request"),
    )
    provider = MiMoTTSProvider(
        base_url="https://api.xiaomimimo.com/v1/chat/completions",
        api_key="key",
        model_name="mimo-v2.5-tts",
        extra_config={"audio_format": "pcm16"},
    )
    with pytest.raises(ValueError, match="pcm_sample_rate"):
        provider.synthesize(TTSRequest(text="Hello"))


def test_audio_connection_test_never_synthesizes(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai.tts.openai_compatible.provider_http.post",
        lambda *_args, **_kwargs: pytest.fail("connection test must not synthesize audio"),
    )
    provider = OpenAICompatibleTTSProvider(
        base_url="https://voice.example/custom/speech", api_key="key", model_name="tts",
    )
    assert "no billable request" in provider.test_connection()


def test_mimo_tts_uses_chat_completion_schema_and_decodes_audio(monkeypatch):
    called: dict[str, object] = {}
    class Response:
        headers: dict[str, str] = {}
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"audio": {"data": base64.b64encode(b"wav-bytes").decode("ascii")}}}]}
    def fake_post(url, **kwargs):
        called["url"], called["payload"] = url, kwargs["json"]
        return Response()
    monkeypatch.setattr("app.services.ai.tts.mimo.provider_http.post", fake_post)
    result = MiMoTTSProvider(base_url="https://api.xiaomimimo.com/v1/chat/completions", api_key="key", model_name="mimo-v2.5-tts").synthesize(TTSRequest(text="Hello", voice="Chloe"))
    assert called["url"] == "https://api.xiaomimimo.com/v1/chat/completions"
    assert called["payload"]["messages"][-1] == {"role": "assistant", "content": "Hello"}
    assert result.audio == b"wav-bytes" and result.extension == "wav"


def test_mimo_asr_uses_chat_completion_audio_part(monkeypatch, tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"wave")
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "hello world"}}]}
    monkeypatch.setattr("app.services.ai.asr.mimo.provider_http.post", lambda *_args, **_kwargs: Response())
    result = MiMoASRProvider(base_url="https://api.xiaomimimo.com/v1/chat/completions", api_key="key", model_name="mimo-v2.5-asr").transcribe(str(audio))
    assert result.text == "hello world"


def test_azure_fast_transcription_parser_normalizes_milliseconds_to_seconds():
    segments = AzureSpeechASRProvider._segments(
        {
            "phrases": [{
                "text": "hello world", "offsetMilliseconds": 1250, "durationMilliseconds": 900,
                "words": [
                    {"text": "hello", "offsetMilliseconds": 1250, "durationMilliseconds": 400},
                    {"text": "world", "offsetMilliseconds": 1700, "durationMilliseconds": 450},
                ],
            }],
        },
        include_words=True,
    )
    assert segments[0].start == 1.25 and segments[0].end == 2.15
    assert [(word.text, word.start, word.end) for word in segments[0].words] == [
        ("hello", 1.25, 1.65), ("world", 1.7, 2.15),
    ]


def test_provider_read_masks_api_key():
    response = _read(AIProvider(id=3, name="secret", capability="llm", provider_type="openai_compatible", api_key="sk-very-secret-key", model_name="model"))
    assert response.api_key_masked is not None
    assert "very-secret" not in response.api_key_masked
    assert "sk-very-secret-key" not in response.model_dump_json()
    assert response.capabilities == ["generate_json", "generate_text"]


def test_provider_error_and_url_redaction_are_safe_with_blank_or_query_credentials():
    assert redact_provider_error("request failed", "") == "request failed"
    assert "secret" not in redact_provider_error("failed token=secret", "secret")
    assert "header-secret" not in redact_provider_error("Headers: Authorization: Bearer header-secret", None)
    safe_url = sanitize_url("https://example.test/v1?api_key=secret&region=us")
    assert safe_url is not None and "secret" not in safe_url and "region=us" in safe_url


def test_provider_test_response_reports_static_capabilities_without_leaking_key(monkeypatch):
    engine = _engine()
    class Provider:
        def test_connection(self):
            raise RuntimeError("request rejected for secret-value")
    monkeypatch.setattr(providers_api, "create_provider", lambda *_args: Provider())
    with Session(engine) as session:
        provider = AIProvider(name="private", capability="asr", provider_type="mimo_asr", base_url="https://example.test", api_key="secret-value", model_name="mimo", enabled_capabilities='["transcribe"]', enabled_formats="[]")
        session.add(provider); session.commit(); session.refresh(provider)
        response = providers_api.test_ai_provider(provider.id, ProviderTestRequest(), session)
    assert response.ok is False
    assert response.capabilities == ["transcribe"]
    assert response.verification_level == "configuration"
    assert "secret-value" not in response.message


def test_provider_catalog_and_draft_test_require_only_no_cost_configuration(monkeypatch):
    class Provider:
        def test_connection(self): return "configured only"
    monkeypatch.setattr(providers_api, "create_provider", lambda *_args: Provider())
    draft = ProviderTestRequest(
        name="draft",
        capability="tts",
        provider_type="openai_audio_tts",
        base_url="https://voice.example/custom/speech",
        api_key="draft-secret",
        model_name="tts-model",
        extra_config={"default_voice": "alloy"}, enabled_capabilities=["synthesize"], enabled_formats=["wav"],
    )
    response = providers_api.test_provider_draft(draft)
    assert response.ok is True
    assert response.verification_level == "configuration"
    assert response.capabilities == ["synthesize"]


def test_provider_create_rejects_undeclared_extra_config_and_disabled_default():
    engine = _engine()
    with Session(engine) as session:
        with pytest.raises(HTTPException) as unknown:
            providers_api.create_ai_provider(
                providers_api.AIProviderCreate(
                    name="unsafe", capability="tts", provider_type="openai_audio_tts",
                    base_url="https://voice.example/speech", api_key="secret", model_name="tts",
                    extra_config={"headers": {"Authorization": "secret"}},
                ),
                session,
            )
        assert unknown.value.status_code == 422
        with pytest.raises(HTTPException) as disabled:
            providers_api.create_ai_provider(
                providers_api.AIProviderCreate(
                    name="disabled", capability="llm", provider_type="openai_chat_compatible",
                    base_url="https://example.test/v1", api_key="secret", model_name="model",
                    is_enabled=False, is_default=True,
                ),
                session,
            )
        assert disabled.value.status_code == 422


def test_asr_router_honours_independent_scene_switches(monkeypatch):
    engine = _engine()
    remote = object()
    monkeypatch.setattr(asr_router, "get_provider", lambda *_args, **_kwargs: remote)
    with Session(engine) as session:
        session.add(AIProvider(name="remote", capability="asr", provider_type="openai_audio_asr", base_url="https://example.test/v1", api_key="key", model_name="asr", is_default=True))
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
        session.add(AIProvider(name="remote", capability="asr", provider_type="openai_whisper_asr", base_url="https://example.test/v1", api_key="key", model_name="whisper-1", is_default=True))
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


def test_user_boundaries_reject_invalid_dependency_combinations():
    descriptor = get_adapter_descriptor("asr", "openai_audio_asr")
    with pytest.raises(ProviderConfigurationError, match="requires transcribe"):
        validate_provider_boundaries(descriptor, "asr", {"word_timestamps"}, set())
    with pytest.raises(ProviderConfigurationError, match="requires at least one output format"):
        validate_provider_boundaries(get_adapter_descriptor("tts", "openai_audio_tts"), "tts", {"synthesize"}, set())


def test_asr_settings_get_is_read_only_when_no_settings_row_exists():
    engine = _engine()
    with Session(engine) as session:
        assert session.get(ASRSceneSetting, 1) is None
        response = providers_api.get_asr_scene_settings(session)
        assert response.material_transcription_use_local is True
        assert session.get(ASRSceneSetting, 1) is None


def test_generated_word_selection_uses_single_structured_response(monkeypatch):
    engine = _engine()
    class Provider:
        def generate_json(self, **_kwargs): return {"title": "Trip", "body": "I travel with apple.", "used_words": ["apple"], "unused_words": ["book"]}
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


def test_llm_json_fence_parser_tolerates_common_invalid_wrapping():
    assert extract_json_object("```json\n{\"title\": \"Trip\"}\n```") == {"title": "Trip"}


def test_invalid_llm_json_does_not_issue_a_second_generation(monkeypatch):
    engine = _engine()
    calls = {"json": 0, "text": 0}
    class Provider:
        def generate_json(self, **_kwargs):
            calls["json"] += 1
            raise ValueError("invalid response")
        def generate_text(self, **_kwargs):
            calls["text"] += 1
            return "should not be called"
    record = AIProvider(id=7, name="fake", capability="llm", provider_type="openai_compatible", base_url="x", model_name="x")
    monkeypatch.setattr(text_generation_service, "require_provider_capabilities", lambda *_args, **_kwargs: record)
    monkeypatch.setattr(text_generation_service, "get_provider", lambda *_args: Provider())
    with Session(engine) as session:
        session.add(WordCollection(material_id=1, sentence_id=1, word_text="apple", normalized_word="apple")); session.commit()
        with pytest.raises(ValueError, match="invalid structured"):
            text_generation_service.create_generated_practice(session, TextGenerationRequest(word_selection="manual", word_collection_ids=[1], target_language="en", difficulty="beginner", desired_length=80))
    assert calls == {"json": 1, "text": 0}


def test_tts_job_creates_material_and_sentences(monkeypatch, tmp_path: Path):
    engine = _engine()
    old_engine, old_data_dir = tts_service.engine, tts_service.settings.data_dir
    monkeypatch.setattr(tts_service, "engine", engine)
    tts_service.settings.data_dir = str(tmp_path)
    class Provider:
        def synthesize(self, _request): return TTSResult(audio=b"audio")
    monkeypatch.setattr(tts_service, "get_provider", lambda *_args: Provider())
    def fake_normalize(_result, *, index, output_dir):
        target = output_dir / f"{index:04d}.wav"
        target.write_bytes(b"wav")
        return target
    monkeypatch.setattr(tts_service, "_normalize_sentence_audio", fake_normalize)
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
            assert all(item.clip_audio_path.endswith(".wav") for item in session.exec(select(Sentence).where(Sentence.material_id == 1)).all())
    finally:
        tts_service.settings.data_dir = old_data_dir
        monkeypatch.setattr(tts_service, "engine", old_engine)


def test_raw_pcm_is_normalized_with_explicit_ffmpeg_parameters(monkeypatch, tmp_path: Path):
    commands: list[list[str]] = []

    def fake_ffmpeg(command, *, operation):
        commands.append(command)
        Path(command[-1]).write_bytes(b"wav")

    monkeypatch.setattr(tts_service, "_ffmpeg", fake_ffmpeg)
    result = TTSResult(
        audio=b"pcm",
        extension="pcm",
        raw_pcm=RawPCMFormat(sample_rate=16000, channels=2, sample_format="s16le"),
    )
    output = tts_service._normalize_sentence_audio(result, index=1, output_dir=tmp_path)
    assert output.name == "0001.wav"
    assert output.read_bytes() == b"wav"
    assert commands == [[
        "ffmpeg", "-y", "-f", "s16le", "-ar", "16000", "-ac", "2",
        "-i", str(tmp_path / "0001.source.pcm"), "-vn", "-ar", "24000", "-ac", "1",
        "-c:a", "pcm_s16le", str(tmp_path / "0001.normalizing.wav"),
    ]]
    assert not (tmp_path / "0001.source.pcm").exists()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is required for the PCM integration check")
def test_raw_pcm_normalization_creates_a_playable_wav(tmp_path: Path):
    # One second of 16-bit little-endian mono silence at 16 kHz.
    result = TTSResult(
        audio=b"\x00\x00" * 16000,
        extension="pcm",
        raw_pcm=RawPCMFormat(sample_rate=16000, channels=1, sample_format="s16le"),
    )
    output = tts_service._normalize_sentence_audio(result, index=1, output_dir=tmp_path)
    assert output.suffix == ".wav"
    assert output.read_bytes().startswith(b"RIFF")
    assert 0.9 <= tts_service.get_audio_duration(output) <= 1.1
