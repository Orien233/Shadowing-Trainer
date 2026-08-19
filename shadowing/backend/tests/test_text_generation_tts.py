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

def test_generated_word_selection_uses_single_structured_response(monkeypatch):
    engine = _engine()
    class Provider:
        def generate_json(self, **_kwargs): return {"title": "Trip", "body": "I travel with apple.", "used_words": ["apple"], "unused_words": ["book"]}
    record = AIProvider(id=7, name="fake", capability="llm", provider_type="openai_chat_compatible", base_url="x", model_name="x")
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
    record = AIProvider(id=7, name="fake", capability="llm", provider_type="openai_chat_compatible", base_url="x", model_name="x")
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
            provider_type="openai_audio_tts",
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
            name="tts", capability="tts", provider_type="openai_audio_tts",
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
            name="tts", capability="tts", provider_type="openai_audio_tts",
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
            provider = AIProvider(name="tts", capability="tts", provider_type="openai_audio_tts", base_url="https://example.test/audio/speech", api_key="key", model_name="tts")
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
