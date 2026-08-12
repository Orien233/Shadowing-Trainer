from __future__ import annotations

import base64
import asyncio
import json
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
from app.schemas.text_practice import TextGenerationRequest, TTSOptions
from app.services import asr_router, evaluation_service, job_service, text_generation_service, tts_service
from app.services.ai.asr.local_whisper import LocalWhisperASRProvider
from app.services import local_whisper_runtime
from app.services.local_whisper_runtime import LocalWhisperStatus
from app.services.vad_service import TrimmedAudioResult
from app.services.ai.audio_types import ProviderCapability, RawPCMFormat, TTSResult
from app.services.ai.tts.base import TTSRequest
from app.services.ai.tts.openai_compatible import OpenAICompatibleTTSProvider
from app.services.ai.tts.mimo import MiMoTTSProvider
from app.services.ai.asr.mimo import MiMoASRProvider
from app.services.ai.asr.openai_compatible import OpenAIWhisperASRProvider
from app.services.ai.asr._helpers import openai_verbose_result
from app.services.ai.asr.azure_speech import AzureSpeechASRProvider
from app.services.ai.adapter_registry import catalog_payload, get_adapter_descriptor
from app.services.ai.llm._shared import extract_json_object
from app.services.provider_security import redact_provider_error, sanitize_url
from app.services.provider_factory import ProviderConfigurationError, create_provider, get_declared_capabilities, get_enabled_capabilities, validate_provider_boundaries
from app.api import jobs as jobs_api, providers as providers_api
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
    assert all(item["preset"] is True and isinstance(item["preset_defaults"], dict) for item in catalog)
    assert next(item for item in catalog if item["key"] == "openai_audio_tts")["preset_defaults"]["base_url"].endswith("/audio/speech")
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


def test_openai_tts_keeps_language_internal_for_base_compatible_endpoints(monkeypatch):
    called: dict[str, object] = {}

    class Response:
        content = b"audio"
        headers: dict[str, str] = {}

        def raise_for_status(self): pass

    def fake_post(_url, **kwargs):
        called["payload"] = kwargs["json"]
        return Response()

    monkeypatch.setattr("app.services.ai.tts.openai_compatible.provider_http.post", fake_post)
    provider = OpenAICompatibleTTSProvider(
        base_url="https://voice.example/custom/speech",
        api_key="key",
        model_name="model",
    )
    result = provider.synthesize(TTSRequest(text="こんにちは。", language="ja"))
    assert "instructions" not in called["payload"]
    assert result.provider_metadata["language"] == "ja"


def test_openai_tts_sends_language_instruction_only_after_explicit_opt_in(monkeypatch):
    called: dict[str, object] = {}

    class Response:
        content = b"audio"
        headers: dict[str, str] = {}

        def raise_for_status(self): pass

    def fake_post(_url, **kwargs):
        called["payload"] = kwargs["json"]
        return Response()

    monkeypatch.setattr("app.services.ai.tts.openai_compatible.provider_http.post", fake_post)
    provider = OpenAICompatibleTTSProvider(
        base_url="https://voice.example/custom/speech",
        api_key="key",
        model_name="model",
        extra_config={"instructions": "Use a warm tone.", "send_language_instruction": True},
    )
    provider.synthesize(TTSRequest(text="こんにちは。", language="ja"))
    assert called["payload"]["instructions"] == "Use a warm tone. Speak the input in ja."


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
    result = MiMoTTSProvider(base_url="https://api.xiaomimimo.com/v1/chat/completions", api_key="key", model_name="mimo-v2.5-tts").synthesize(TTSRequest(text="Hello", voice="Chloe", language="ar"))
    assert called["url"] == "https://api.xiaomimimo.com/v1/chat/completions"
    assert called["payload"]["messages"][0] == {"role": "user", "content": "Speak the input in ar."}
    assert called["payload"]["messages"][-1] == {"role": "assistant", "content": "Hello"}
    assert result.audio == b"wav-bytes" and result.extension == "wav"
    assert result.provider_metadata["language"] == "ar"


def test_mimo_asr_uses_chat_completion_audio_part(monkeypatch, tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"wave")
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "hello world"}}]}
    monkeypatch.setattr("app.services.ai.asr.mimo.provider_http.post", lambda *_args, **_kwargs: Response())
    result = MiMoASRProvider(base_url="https://api.xiaomimimo.com/v1/chat/completions", api_key="key", model_name="mimo-v2.5-asr").transcribe(str(audio))
    assert result.text == "hello world"


def test_openai_asr_prefers_task_language_and_reduces_bcp47_to_base_code(monkeypatch, tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"wave")
    requests: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self): pass
        def json(self): return {"text": "hello"}

    def fake_post(_url, **kwargs):
        requests.append(kwargs["data"])
        return Response()

    monkeypatch.setattr("app.services.ai.asr.openai_compatible.provider_http.post", fake_post)
    provider = OpenAIWhisperASRProvider(
        base_url="https://example.test/v1",
        api_key="key",
        model_name="whisper-1",
        extra_config={"language": "ja"},
    )

    provider.transcribe(str(audio), language="zh-CN")
    provider.transcribe(str(audio))

    assert requests[0]["language"] == "zh"
    assert requests[1]["language"] == "ja"


def test_openai_asr_requests_word_and_segment_timestamps(monkeypatch, tmp_path: Path):
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"wave")
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {
                "text": "hello world",
                "segments": [{"start": 0.1, "end": 1.2, "text": "hello world"}],
                "words": [
                    {"word": "hello", "start": 0.1, "end": 0.6},
                    {"word": "world", "start": 0.7, "end": 1.2},
                ],
            }

    def fake_post(_url, **kwargs):
        captured["data"] = kwargs["data"]
        return Response()

    monkeypatch.setattr("app.services.ai.asr.openai_compatible.provider_http.post", fake_post)
    provider = OpenAIWhisperASRProvider(
        base_url="https://example.test/v1",
        api_key="key",
        model_name="whisper-1",
    )

    provider.transcribe(str(audio), word_timestamps=True)

    assert captured["data"]["timestamp_granularities[]"] == ["word", "segment"]


def test_openai_verbose_words_only_response_rebuilds_a_nonzero_segment_timeline():
    text, segments = openai_verbose_result(
        {
            "duration": 2.0,
            "text": "hello world",
            "words": [
                {"word": "hello", "start": 0.15, "end": 0.7},
                {"word": "world", "start": 0.8, "end": 1.6},
            ],
        },
        include_words=True,
    )

    assert text == "hello world"
    assert len(segments) == 1
    assert (segments[0].start, segments[0].end) == (0.15, 1.6)
    assert [word.text for word in segments[0].words] == ["hello", "world"]


@pytest.mark.parametrize(
    ("task_language", "provider_language"),
    [
        ("en", "en"),
        ("en-US", "en"),
        ("zh-CN", "zh"),
        ("zh-TW", "zh"),
        ("auto", "auto"),
        ("und", "auto"),
    ],
)
def test_mimo_asr_maps_task_language_to_its_documented_values(
    monkeypatch,
    tmp_path: Path,
    task_language: str,
    provider_language: str,
):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"wave")
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "hello"}}]}

    def fake_post(_url, **kwargs):
        captured["payload"] = kwargs["json"]
        return Response()

    monkeypatch.setattr("app.services.ai.asr.mimo.provider_http.post", fake_post)
    MiMoASRProvider(
        base_url="https://api.xiaomimimo.com/v1/chat/completions",
        api_key="key",
        model_name="mimo-v2.5-asr",
        extra_config={"language": "ja"},
    ).transcribe(str(audio), language=task_language)

    assert captured["payload"]["asr_options"]["language"] == provider_language


def test_mimo_asr_rejects_an_unsupported_task_language_before_network(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai.asr.mimo.provider_http.post",
        lambda *_args, **_kwargs: pytest.fail("Unsupported languages must not reach MiMo"),
    )
    provider = MiMoASRProvider(
        base_url="https://api.xiaomimimo.com/v1/chat/completions",
        api_key="key",
        model_name="mimo-v2.5-asr",
    )

    with pytest.raises(ValueError, match=r"MiMo ASR.*'ja'.*not supported"):
        provider.transcribe("file-does-not-need-to-exist.wav", language="ja")


def test_local_whisper_receives_task_language(monkeypatch):
    captured: dict[str, object] = {}

    def fake_transcribe(_audio_path, **kwargs):
        captured.update(kwargs)
        return [{"text": "hello", "start": 0.0, "end": 1.0, "words": []}]

    monkeypatch.setattr("app.services.ai.asr.local_whisper.transcribe_audio", fake_transcribe)
    result = LocalWhisperASRProvider(extra_config={"language": "ja"}).transcribe(
        "recording.wav",
        language="zh-TW",
    )

    assert result.text == "hello"
    assert captured["language"] == "zh"


def test_asr_router_passes_task_language_to_provider(monkeypatch):
    engine = _engine()
    captured: dict[str, object] = {}

    class Provider:
        def transcribe(self, _audio_path, *, word_timestamps, language):
            captured["segments_language"] = language
            return type("Result", (), {"as_legacy_segments": lambda self: []})()

        def transcribe_text(self, _audio_path, *, language):
            captured["text_language"] = language
            return "hello"

    monkeypatch.setattr(asr_router, "engine", engine)
    monkeypatch.setattr(asr_router, "get_asr_provider", lambda *_args, **_kwargs: Provider())
    assert asr_router.transcribe_for_scene("recording_evaluation", "recording.wav", language="fr") == []
    assert asr_router.transcribe_text_for_scene("recording_evaluation", "recording.wav", language="de") == "hello"
    assert captured == {"segments_language": "fr", "text_language": "de"}


def test_evaluation_forwards_content_language_to_recording_asr(monkeypatch):
    captured: dict[str, object] = {}

    def stop_after_asr(scene, audio_path, *, language=None):
        captured.update({"scene": scene, "audio_path": audio_path, "language": language})
        raise RuntimeError("stop after ASR handoff")

    monkeypatch.setattr(
        evaluation_service,
        "create_trimmed_audio",
        lambda recording_path, **_kwargs: TrimmedAudioResult(
            audio_path=recording_path,
            metadata={},
            tags=(),
            should_cleanup=False,
        ),
    )
    monkeypatch.setattr(evaluation_service, "transcribe_text_for_scene", stop_after_asr)

    with pytest.raises(RuntimeError, match="stop after ASR handoff"):
        evaluation_service.evaluate_recording(
            "bonjour",
            1.0,
            "recording.wav",
            content_language="fr",
        )

    assert captured == {
        "scene": asr_router.RECORDING_EVALUATION,
        "audio_path": "recording.wav",
        "language": "fr",
    }


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
        response = providers_api.test_ai_provider(
            provider.id,
            ProviderTestRequest(test_mode="network"),
            session,
        )
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


def test_live_provider_test_is_explicitly_billable_and_uses_a_small_request(monkeypatch):
    class Provider:
        def generate_text(self, **kwargs):
            assert kwargs["user_prompt"] == "Return OK."
            return "OK"

    monkeypatch.setattr(providers_api, "create_provider", lambda *_args: Provider())
    provider = AIProvider(
        name="live", capability="llm", provider_type="openai_chat_compatible",
        base_url="https://example.test/v1", api_key="secret", model_name="model",
        enabled_capabilities='["generate_text", "generate_json"]', enabled_formats='["response_format"]',
    )
    response = providers_api._test_provider(provider, "inference")
    assert response.ok is True
    assert response.verification_level == "inference"
    assert response.billable is True
    assert "live LLM generation" in response.message


def test_local_whisper_status_is_safe_when_optional_package_is_missing(monkeypatch):
    monkeypatch.setattr(local_whisper_runtime, "_is_installed", lambda: False)
    status = local_whisper_runtime.get_local_whisper_status()
    assert status.installed is False
    assert status.runtime_ready is False
    assert "requirements-local-whisper" in (status.error or "")


def test_local_whisper_status_marks_an_uncached_offline_model_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(local_whisper_runtime, "_is_installed", lambda: True)
    monkeypatch.setattr(local_whisper_runtime, "_model_directory", lambda: tmp_path)
    old_download = local_whisper_runtime.settings.whisper_allow_download
    local_whisper_runtime.settings.whisper_allow_download = False
    try:
        status = local_whisper_runtime.get_local_whisper_status()
        assert status.runtime_ready is False
        assert "not cached" in (status.error or "")
    finally:
        local_whisper_runtime.settings.whisper_allow_download = old_download


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
        result = providers_api.update_asr_scene_settings(
            ASRSceneSettingUpdate(material_transcription_use_local=False),
            session,
        )
        # A direct API call cannot persist an impossible remote material route;
        # it is reconciled to the viable Local Whisper route.
        assert result.material_transcription_use_local is True


def test_mimo_recording_asr_falls_back_to_local_for_an_unsupported_task_language(monkeypatch):
    engine = _engine()
    remote_calls: list[str] = []
    ready_local = LocalWhisperStatus(
        installed=True, runtime_ready=True, model_loaded=False, model_cached=True,
        will_download_on_first_use=False, model_name="small", device="cpu", compute_type="int8",
        model_dir="data/models/whisper", allow_download=True, error=None,
    )

    class RemoteMiMo:
        def provider_language(self, language):
            if language == "ja":
                from app.services.ai.asr.base import UnsupportedASRLanguageError
                raise UnsupportedASRLanguageError("MiMo ASR does not support task language 'ja'.")
            return language

        def transcribe_text(self, *_args, **_kwargs):
            remote_calls.append("transcribe")
            return "should not run"

    monkeypatch.setattr(asr_router, "get_local_whisper_status", lambda: ready_local)
    monkeypatch.setattr(asr_router, "get_provider", lambda *_args, **_kwargs: RemoteMiMo())
    with Session(engine) as session:
        session.add(AIProvider(
            name="mimo", capability="asr", provider_type="mimo_asr",
            base_url="https://example.test", api_key="key", model_name="mimo",
            is_default=True,
        ))
        session.add(ASRSceneSetting(recording_evaluation_use_local=False))
        session.commit()

        provider = asr_router.get_asr_provider(
            session,
            asr_router.RECORDING_EVALUATION,
            language="ja",
        )

    assert isinstance(provider, LocalWhisperASRProvider)
    assert remote_calls == []


def test_mimo_recording_asr_fails_readably_without_a_local_language_fallback(monkeypatch):
    engine = _engine()
    missing_local = LocalWhisperStatus(
        installed=False, runtime_ready=False, model_loaded=False, model_cached=False,
        will_download_on_first_use=False, model_name="small", device="cpu", compute_type="int8",
        model_dir="data/models/whisper", allow_download=True, error="Local Whisper is not installed.",
    )
    remote_calls: list[str] = []

    class RemoteMiMo:
        def provider_language(self, language):
            from app.services.ai.asr.base import UnsupportedASRLanguageError
            raise UnsupportedASRLanguageError(
                f"MiMo ASR supports only English (en) or Chinese (zh); task language '{language}' is not supported."
            )

        def transcribe_text(self, *_args, **_kwargs):
            remote_calls.append("transcribe")
            return "should not run"

    monkeypatch.setattr(asr_router, "get_local_whisper_status", lambda: missing_local)
    monkeypatch.setattr(asr_router, "get_provider", lambda *_args, **_kwargs: RemoteMiMo())
    with Session(engine) as session:
        session.add(AIProvider(
            name="mimo", capability="asr", provider_type="mimo_asr",
            base_url="https://example.test", api_key="key", model_name="mimo",
            is_default=True,
        ))
        session.add(ASRSceneSetting(recording_evaluation_use_local=False))
        session.commit()

        with pytest.raises(
            ProviderConfigurationError,
            match=r"Local Whisper is not installed.*task language 'ja'.*not supported",
        ):
            asr_router.get_asr_provider(
                session,
                asr_router.RECORDING_EVALUATION,
                language="ja",
            )

    assert remote_calls == []


def test_remote_only_install_uses_remote_asr_when_local_whisper_is_missing(monkeypatch):
    engine = _engine()
    missing_local = LocalWhisperStatus(
        installed=False, runtime_ready=False, model_loaded=False, model_cached=False,
        will_download_on_first_use=False, model_name="small", device="cpu", compute_type="int8",
        model_dir="data/models/whisper", allow_download=True, error="Local Whisper is not installed.",
    )
    remote = object()
    monkeypatch.setattr(asr_router, "get_local_whisper_status", lambda: missing_local)
    monkeypatch.setattr(asr_router, "get_provider", lambda *_args, **_kwargs: remote)
    with Session(engine) as session:
        session.add(AIProvider(
            name="remote", capability="asr", provider_type="openai_audio_asr",
            base_url="https://example.test/v1", api_key="key", model_name="asr", is_default=True,
        ))
        session.add(ASRSceneSetting(material_transcription_use_local=True, recording_evaluation_use_local=True))
        session.commit()
        settings = providers_api.get_asr_scene_settings(session)
        assert settings.material_transcription_effective_route == "remote"
        assert settings.recording_evaluation_effective_route == "remote"
        assert settings.material_transcription_local_available is False
        assert asr_router.get_asr_provider(session, asr_router.MATERIAL_TRANSCRIPTION) is remote


def test_asr_scene_is_explicitly_unavailable_without_local_or_remote(monkeypatch):
    engine = _engine()
    missing_local = LocalWhisperStatus(
        installed=False, runtime_ready=False, model_loaded=False, model_cached=False,
        will_download_on_first_use=False, model_name="small", device="cpu", compute_type="int8",
        model_dir="data/models/whisper", allow_download=True, error="Local Whisper is not installed.",
    )
    monkeypatch.setattr(asr_router, "get_local_whisper_status", lambda: missing_local)
    with Session(engine) as session:
        session.add(ASRSceneSetting())
        session.commit()
        settings = providers_api.get_asr_scene_settings(session)
        assert settings.material_transcription_available is False
        assert settings.material_transcription_effective_route == "unavailable"
        with pytest.raises(ProviderConfigurationError, match="No ASR route is available"):
            asr_router.get_asr_provider(session, asr_router.MATERIAL_TRANSCRIPTION)


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


def test_generated_word_selection_is_scoped_to_target_language():
    engine = _engine()
    with Session(engine) as session:
        english = WordCollection(material_id=1, sentence_id=1, word_text="travel", normalized_word="travel", language="en")
        japanese = WordCollection(material_id=2, sentence_id=2, word_text="旅行", normalized_word="旅行", language="ja")
        session.add(english)
        session.add(japanese)
        session.commit()

        selected = text_generation_service._select_collections(
            session,
            TextGenerationRequest(word_selection="random", random_word_count=1, target_language="ja"),
        )
        assert [item.id for item in selected] == [japanese.id]

        with pytest.raises(ValueError, match="target language"):
            text_generation_service._select_collections(
                session,
                TextGenerationRequest(
                    word_selection="manual",
                    word_collection_ids=[english.id],
                    target_language="ja",
                ),
            )


def test_generation_prompt_names_the_canonical_target_language():
    request = TextGenerationRequest(target_language="ja", desired_length=80)
    payload = json.loads(text_generation_service._build_prompt(request, ["旅行"], "travel"))
    assert payload["target_language"] == {
        "code": "ja",
        "name": "Japanese",
        "native_name": "日本語",
    }
    assert "entirely in Japanese" in payload["requirements"]


def test_generated_word_fallback_uses_word_boundaries_for_spaced_languages():
    assert text_generation_service._word_appears_in_body("he", "He is here.", "en")
    assert not text_generation_service._word_appears_in_body("he", "The book is here.", "en")
    assert text_generation_service._word_appears_in_body("旅行", "旅行が好きです。", "ja")


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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("你好。欢迎学习！再见？", ["你好。", "欢迎学习！", "再见？"]),
        ("これは文です。次の文です！", ["これは文です。", "次の文です！"]),
        ("مرحبا؟كيف حالك؟", ["مرحبا؟", "كيف حالك؟"]),
        ("यह पहला वाक्य है।यह दूसरा है॥", ["यह पहला वाक्य है।", "यह दूसरा है॥"]),
    ],
)
def test_tts_sentence_splitter_supports_no_space_multilingual_scripts(text, expected):
    parts = tts_service.split_practice_sentences(text)
    assert parts == expected
    assert "".join(parts) == text


def test_tts_sentence_splitter_preserves_decimal_and_domain_periods():
    assert tts_service.split_practice_sentences(
        "The value is 3.14 and the site is example.com. Next sentence."
    ) == [
        "The value is 3.14 and the site is example.com.",
        "Next sentence.",
    ]


def test_tts_options_validate_explicit_language_and_queue_freezes_target_language(monkeypatch):
    engine = _engine()
    captured_payloads: list[dict] = []

    def fake_enqueue(_session, _kind, payload):
        captured_payloads.append(payload)
        return type("QueuedJob", (), {"id": "queued-tts"})()

    monkeypatch.setattr(
        "app.services.job_service.enqueue_job",
        fake_enqueue,
    )
    with pytest.raises(ValueError, match="Unsupported language"):
        TTSOptions(language="nl")

    with Session(engine) as session:
        provider = AIProvider(
            name="tts",
            capability="tts",
            provider_type="openai_compatible",
            base_url="https://example.test/audio/speech",
            api_key="key",
            model_name="tts",
            is_default=True,
        )
        practice = TextPractice(
            title="Japanese",
            body="こんにちは。",
            source_type="import",
            target_language="ja",
        )
        session.add(provider)
        session.add(practice)
        session.commit()
        session.refresh(practice)

        tts_service.queue_tts(session, practice, TTSOptions())
        session.refresh(practice)
        assert TTSOptions.model_validate_json(practice.tts_options_json).language == "ja"
        assert captured_payloads[0]["snapshot"] == {
            "title": "Japanese",
            "body": "こんにちは。",
            "target_language": "ja",
            "translation_language": "zh-CN",
            "provider_id": provider.id,
            "options": {"speed_preset": "normal", "accent": None, "gender": None, "voice": None, "model": None, "provider_id": None, "language": "ja"},
        }

        with pytest.raises(ValueError, match="must match"):
            tts_service.queue_tts(session, practice, TTSOptions(language="ar"))


def test_edit_after_queue_invalidates_tts_snapshot_without_synthesis(monkeypatch):
    engine = _engine()
    captured: dict[str, object] = {}

    def fake_enqueue(_session, _kind, payload):
        captured["payload"] = payload
        return type("QueuedJob", (), {"id": "stale-job"})()

    monkeypatch.setattr("app.services.job_service.enqueue_job", fake_enqueue)
    monkeypatch.setattr(tts_service, "engine", engine)
    monkeypatch.setattr(
        tts_service,
        "get_provider",
        lambda *_args: pytest.fail("An obsolete TTS job must not call the provider"),
    )
    with Session(engine) as session:
        provider = AIProvider(
            name="tts", capability="tts", provider_type="openai_compatible",
            base_url="https://example.test/audio/speech", api_key="key", model_name="tts",
            is_default=True,
        )
        practice = TextPractice(
            title="Original", body="Original text.", source_type="import", target_language="en"
        )
        session.add(provider)
        session.add(practice)
        session.commit()
        session.refresh(practice)
        tts_service.queue_tts(session, practice, TTSOptions())
        text_generation_service.update_practice(
            session, practice, title="Edited title", body=None, target_language=None, translation_language=None
        )

    with pytest.raises(tts_service.TTSJobObsoleteError, match="superseded"):
        tts_service.run_tts_synthesis("stale-job", captured["payload"])

    with Session(engine) as session:
        practice = session.get(TextPractice, 1)
        assert practice.tts_status == "not_requested"
        assert practice.tts_job_id is None
        assert practice.material_id is None
        assert session.exec(select(Material)).all() == []


def test_tts_final_write_rechecks_snapshot_and_uses_job_isolated_audio_paths(monkeypatch, tmp_path: Path):
    engine = _engine()
    captured: dict[str, object] = {}
    synthesis_calls = 0

    def fake_enqueue(_session, _kind, payload):
        captured["payload"] = payload
        return type("QueuedJob", (), {"id": "running-job"})()

    class Provider:
        def synthesize(self, _request):
            nonlocal synthesis_calls
            synthesis_calls += 1
            # Simulate an edit made while a remote provider is producing audio.
            with Session(engine) as edit_session:
                practice = edit_session.get(TextPractice, 1)
                text_generation_service.update_practice(
                    edit_session,
                    practice,
                    title=None,
                    body="Edited while TTS was running.",
                    target_language=None,
                    translation_language=None,
                )
            return TTSResult(audio=b"audio")

    monkeypatch.setattr("app.services.job_service.enqueue_job", fake_enqueue)
    monkeypatch.setattr(tts_service, "engine", engine)
    monkeypatch.setattr(tts_service.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(tts_service, "get_provider", lambda *_args: Provider())
    async def fake_translate(sentences, **_kwargs):
        return ["" for _ in sentences]
    monkeypatch.setattr(tts_service, "translate_sentences", fake_translate)
    monkeypatch.setattr(tts_service, "update_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        tts_service,
        "_normalize_sentence_audio",
        lambda _result, *, index, output_dir: (output_dir / f"{index:04d}.wav"),
    )
    monkeypatch.setattr(tts_service, "_merge_audio", lambda _parts, target: target.write_bytes(b"merged"))
    monkeypatch.setattr(tts_service, "get_audio_duration", lambda _path: 1.0)

    with Session(engine) as session:
        provider = AIProvider(
            name="tts", capability="tts", provider_type="openai_compatible",
            base_url="https://example.test/audio/speech", api_key="key", model_name="tts",
            is_default=True,
        )
        practice = TextPractice(
            title="Original", body="First sentence. Second sentence.", source_type="import", target_language="en"
        )
        session.add(provider)
        session.add(practice)
        session.commit()
        session.refresh(practice)
        tts_service.queue_tts(session, practice, TTSOptions())

    with pytest.raises(tts_service.TTSJobObsoleteError, match="superseded"):
        tts_service.run_tts_synthesis("running-job", captured["payload"])

    job_audio = tmp_path / "audio" / "text_practice_1_running-job.mp3"
    assert not job_audio.exists()
    assert not (tmp_path / "audio" / "sentences" / "text_practice_1_running-job").exists()
    assert synthesis_calls == 1
    assert not (tmp_path / "audio" / "text_practice_1.mp3").exists()
    with Session(engine) as session:
        assert session.exec(select(Material)).all() == []
        assert session.get(TextPractice, 1).tts_job_id is None


def test_failed_tts_job_cannot_mark_newer_job_failed(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(job_service, "engine", engine)

    async def fail_tts(*_args, **_kwargs):
        raise RuntimeError("provider failed")

    monkeypatch.setitem(job_service.JOB_HANDLERS, "tts_synthesis", fail_tts)
    with Session(engine) as session:
        practice = TextPractice(
            title="Current", body="Current text.", source_type="import",
            tts_job_id="newer-job", tts_status="queued",
        )
        old_job = Job(id="stale-job", kind="tts_synthesis", status="running", payload='{"text_practice_id": 1}')
        session.add(practice)
        session.add(old_job)
        session.commit()

    asyncio.run(job_service._run_job("stale-job"))

    with Session(engine) as session:
        assert session.get(Job, "stale-job").status == "failed"
        assert session.get(TextPractice, 1).tts_status == "queued"


def _failed_tts_job_fixture(
    session: Session,
    *,
    job_id: str = "failed-tts",
) -> tuple[TextPractice, Job]:
    options = TTSOptions(language="en")
    practice = TextPractice(
        title="Retryable",
        body="Retry this sentence.",
        source_type="import",
        target_language="en",
        translation_language="zh-CN",
        tts_provider_id=17,
        tts_options_json=options.model_dump_json(),
        tts_status="failed",
        tts_job_id=job_id,
    )
    session.add(practice)
    session.flush()
    snapshot = {
        "title": practice.title,
        "body": practice.body,
        "target_language": practice.target_language,
        "translation_language": practice.translation_language,
        "provider_id": practice.tts_provider_id,
        "options": options.model_dump(mode="json"),
    }
    job = Job(
        id=job_id,
        kind="tts_synthesis",
        status="failed",
        stage="failed",
        error_message="provider unavailable",
        payload=json.dumps(
            {"text_practice_id": practice.id, "snapshot": snapshot},
            ensure_ascii=False,
        ),
    )
    session.add(job)
    session.commit()
    return practice, job


def test_failed_tts_retry_atomically_reclaims_unchanged_practice():
    engine = _engine()
    with Session(engine) as session:
        practice, job = _failed_tts_job_fixture(session)

        retried = job_service.retry_job(session, job.id)

        session.refresh(practice)
        assert retried.status == "queued"
        assert retried.stage == "queued"
        assert retried.error_message is None
        assert practice.tts_job_id == job.id
        assert practice.tts_status == "queued"


def test_failed_tts_retry_rejects_a_newer_queued_or_running_owner():
    engine = _engine()
    with Session(engine) as session:
        practice, old_job = _failed_tts_job_fixture(session)
        newer_job = Job(
            id="newer-tts",
            kind="tts_synthesis",
            status="running",
            payload=old_job.payload,
        )
        practice.tts_job_id = newer_job.id
        practice.tts_status = "queued"
        session.add(newer_job)
        session.add(practice)
        session.commit()

        with pytest.raises(ValueError, match="newer TTS job is already queued or running"):
            job_service.retry_job(session, old_job.id)

        session.refresh(old_job)
        session.refresh(practice)
        assert old_job.status == "failed"
        assert practice.tts_job_id == newer_job.id
        assert practice.tts_status == "queued"


def test_failed_tts_retry_rejects_an_edited_snapshot():
    engine = _engine()
    with Session(engine) as session:
        practice, job = _failed_tts_job_fixture(session)
        practice.body = "Edited after the failed request."
        practice.tts_job_id = None
        practice.tts_status = "not_requested"
        session.add(practice)
        session.commit()

        with pytest.raises(ValueError, match="edited after it was queued"):
            job_service.retry_job(session, job.id)

        session.refresh(job)
        session.refresh(practice)
        assert job.status == "failed"
        assert practice.tts_job_id is None
        assert practice.tts_status == "not_requested"


def test_tts_retry_conflict_api_returns_readable_409(monkeypatch):
    monkeypatch.setattr(
        jobs_api,
        "retry_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("A newer TTS job is already queued or running for this text practice.")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        jobs_api.retry_failed_job("old-tts", session=object())

    assert exc_info.value.status_code == 409
    assert "newer TTS job" in str(exc_info.value.detail)


def test_tts_job_creates_material_and_sentences(monkeypatch, tmp_path: Path):
    engine = _engine()
    old_engine, old_data_dir = tts_service.engine, tts_service.settings.data_dir
    monkeypatch.setattr(tts_service, "engine", engine)
    tts_service.settings.data_dir = str(tmp_path)
    requests: list[TTSRequest] = []

    class Provider:
        def synthesize(self, request):
            requests.append(request)
            return TTSResult(audio=b"audio")
    monkeypatch.setattr(tts_service, "get_provider", lambda *_args: Provider())
    translation_call: dict[str, object] = {}
    async def fake_translate(sentences, *, source_language, target_language):
        translation_call.update({
            "sentences": list(sentences),
            "source_language": source_language,
            "target_language": target_language,
        })
        return ["第一句。", "第二句！"]
    monkeypatch.setattr(tts_service, "translate_sentences", fake_translate)
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
            practice = TextPractice(title="Generated", body="First sentence. Second sentence!", source_type="import", target_language="ja", tts_provider_id=provider.id, tts_job_id="job", tts_options_json='{"speed_preset":"normal", "language":"ja"}')
            session.add(practice); session.commit()
        result = tts_service.run_tts_synthesis("job", {"text_practice_id": 1})
        assert result["material_id"] == 1
        with Session(engine) as session:
            saved_sentences = session.exec(select(Sentence).where(Sentence.material_id == 1).order_by(Sentence.display_order)).all()
            assert len(saved_sentences) == 2
            assert [item.translation for item in saved_sentences] == ["第一句。", "第二句！"]
            assert session.get(Material, 1).status == "ready"
            assert session.get(Material, 1).content_language == "ja"
            assert session.get(Material, 1).translation_language == "zh-CN"
            assert session.get(Material, 1).original_path.endswith("text_practice_1_job.mp3")
            assert session.get(Material, 1).audio_path.endswith("text_practice_1_job.mp3")
            assert all(item.clip_audio_path.endswith(".wav") for item in session.exec(select(Sentence).where(Sentence.material_id == 1)).all())
        assert [request.language for request in requests] == ["ja", "ja"]
        assert translation_call == {
            "sentences": ["First sentence.", "Second sentence!"],
            "source_language": "ja",
            "target_language": "zh-CN",
        }
    finally:
        tts_service.settings.data_dir = old_data_dir
        monkeypatch.setattr(tts_service, "engine", old_engine)


def test_tts_merge_uses_absolute_paths_for_relative_data_directories(monkeypatch, tmp_path: Path):
    """FFmpeg concat files resolve entries from the concat file's directory."""
    monkeypatch.chdir(tmp_path)
    segment = Path("data/audio/sentences/text_practice_1/0001.wav")
    segment.parent.mkdir(parents=True)
    segment.write_bytes(b"wav")
    target = Path("data/audio/text_practice_1.mp3")
    target.parent.mkdir(parents=True, exist_ok=True)
    captured: dict[str, str] = {}

    def fake_ffmpeg(command, *, operation):
        assert operation == "merging normalized TTS sentences"
        captured["concat"] = Path(command[7]).read_text(encoding="utf-8")
        Path(command[-1]).write_bytes(b"mp3")

    monkeypatch.setattr(tts_service, "_ffmpeg", fake_ffmpeg)
    tts_service._merge_audio([segment], target)

    assert captured["concat"] == f"file '{segment.resolve().as_posix()}'\n"
    assert target.read_bytes() == b"mp3"
    assert not target.with_suffix(".concat.txt").exists()


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
