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
    provider = OpenAIAudioTTSProvider(base_url="https://voice.example/custom/speech", api_key="key", model_name="model")
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
    provider = OpenAIAudioTTSProvider(
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
    provider = OpenAIAudioTTSProvider(
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
    result = OpenAIAudioTTSProvider(
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
    provider = OpenAIAudioTTSProvider(
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
