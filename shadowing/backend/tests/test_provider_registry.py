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
from app.models.text_practice import TextPractice
from app.models.word_collection import WordCollection
from app.schemas.ai_provider import ASRSceneSettingUpdate, ProviderTestRequest
from app.schemas.text_practice import TextGenerationRequest, TTSOptions
from app.services import (
    asr_router,
    evaluation_service,
    job_service,
    provider_test_service,
    text_generation_service,
    tts_service,
)
from app.services.ai.asr.local_whisper import LocalWhisperASRProvider
from app.services import local_whisper_runtime
from app.services.local_whisper_runtime import LocalWhisperStatus
from app.services.vad_service import TrimmedAudioResult
from app.services.ai.audio_types import ProviderCapability, RawPCMFormat, TTSResult
from app.services.ai.tts.base import TTSRequest
from app.services.ai.tts.openai_compatible import OpenAIAudioTTSProvider
from app.services.ai.tts.mimo import MiMoTTSProvider
from app.services.ai.asr.mimo import MiMoASRProvider
from app.services.ai.asr.openai_compatible import OpenAIWhisperASRProvider
from app.services.ai.asr._helpers import openai_verbose_result
from app.services.ai.adapter_registry import catalog_payload, get_adapter_descriptor
from app.services.ai.llm._shared import extract_json_object
from app.services.provider_security import redact_provider_error, sanitize_url
from app.services.provider_factory import ProviderConfigurationError, create_provider, get_declared_capabilities, get_enabled_capabilities, validate_provider_boundaries
from app.api import jobs as jobs_api, providers as providers_api
from app.api.providers import _read


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=[AIProvider.__table__, ASRSceneSetting.__table__, TextPractice.__table__, WordCollection.__table__, Job.__table__, Material.__table__, Sentence.__table__])
    return engine


def test_factory_creates_supported_openai_providers():
    llm = create_provider(AIProvider(name="x", capability="llm", provider_type="openai_chat_compatible", base_url="https://example.test/v1", api_key="secret", model_name="model"))
    tts = create_provider(AIProvider(name="x", capability="tts", provider_type="openai_audio_tts", base_url="https://example.test/v1", api_key="secret", model_name="model"))
    asr = create_provider(AIProvider(name="x", capability="asr", provider_type="openai_audio_asr", base_url="https://example.test/v1", api_key="secret", model_name="model"))
    assert llm.__class__.__name__ == "OpenAIChatCompatibleLLMProvider"
    assert tts.__class__.__name__ == "OpenAIAudioTTSProvider"
    assert asr.__class__.__name__ == "OpenAIWhisperASRProvider"


def test_unsupported_adapter_cannot_be_created():
    with pytest.raises(ProviderConfigurationError):
        create_provider(AIProvider(name="azure", capability="tts", provider_type="azure_speech", base_url="https://example.test", api_key="secret", model_name="voice"))


def test_factory_creates_mimo_audio_adapters():
    tts = create_provider(AIProvider(name="mimo", capability="tts", provider_type="mimo_tts", base_url="https://api.xiaomimimo.com/v1/chat/completions", api_key="secret", model_name="mimo-v2.5-tts"))
    asr = create_provider(AIProvider(name="mimo", capability="asr", provider_type="mimo_asr", base_url="https://api.xiaomimimo.com/v1/chat/completions", api_key="secret", model_name="mimo-v2.5-asr"))
    assert tts.__class__.__name__ == "MiMoTTSProvider"
    assert asr.__class__.__name__ == "MiMoASRProvider"


def test_adapter_registry_exposes_only_canonical_types_and_a_safe_catalog():
    assert get_adapter_descriptor("llm", "openai_compatible") is None
    assert get_adapter_descriptor("tts", "openai_compatible") is None
    assert get_adapter_descriptor("asr", "openai_compatible") is None
    catalog = catalog_payload()
    keys = {(item["kind"], item["key"]) for item in catalog}
    assert keys == {("llm", "openai_chat_compatible"), ("tts", "openai_audio_tts"), ("tts", "mimo_tts"), ("asr", "openai_audio_asr"), ("asr", "mimo_asr")}
    assert all(item["preset"] is True and isinstance(item["preset_defaults"], dict) for item in catalog)
    assert next(item for item in catalog if item["key"] == "openai_audio_tts")["preset_defaults"]["base_url"].endswith("/audio/speech")
    assert all("api_key" not in {field["key"] for field in item["config_fields"]} for item in catalog)


def test_unsupported_profiles_are_not_registered():
    assert get_adapter_descriptor("llm", "ollama_chat") is None


def test_adapter_capabilities_are_static_and_safe_to_read():
    llm = AIProvider(name="llm", capability="llm", provider_type="openai_chat_compatible", base_url="https://example.test/v1", model_name="model")
    remote_asr = AIProvider(name="remote", capability="asr", provider_type="openai_audio_asr", base_url="https://example.test/v1", model_name="model")
    mimo_asr = AIProvider(name="mimo", capability="asr", provider_type="mimo_asr", base_url="https://example.test", model_name="model")
    assert get_declared_capabilities(llm) == {ProviderCapability.GENERATE_TEXT, ProviderCapability.GENERATE_JSON}
    assert get_declared_capabilities(remote_asr) == {ProviderCapability.TRANSCRIBE, ProviderCapability.WORD_TIMESTAMPS}
    assert get_declared_capabilities(mimo_asr) == {ProviderCapability.TRANSCRIBE}


def test_provider_read_masks_api_key():
    response = _read(AIProvider(id=3, name="secret", capability="llm", provider_type="openai_chat_compatible", api_key="sk-very-secret-key", model_name="model"))
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
    monkeypatch.setattr(provider_test_service, "create_provider", lambda *_args: Provider())
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
    monkeypatch.setattr(provider_test_service, "create_provider", lambda *_args: Provider())
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

    monkeypatch.setattr(provider_test_service, "create_provider", lambda *_args: Provider())
    provider = AIProvider(
        name="live", capability="llm", provider_type="openai_chat_compatible",
        base_url="https://example.test/v1", api_key="secret", model_name="model",
        enabled_capabilities='["generate_text", "generate_json"]', enabled_formats='["response_format"]',
    )
    response = provider_test_service.test_provider(provider, "inference")
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
