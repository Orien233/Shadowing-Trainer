from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models.material import Material
from app.models.recording import Recording
from app.models.sentence import Sentence
from app.services import job_service, material_processing_service


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(
        engine,
        tables=[Material.__table__, Sentence.__table__, Recording.__table__],
    )
    return engine


@pytest.mark.parametrize("file_type", ["audio", "video"])
def test_material_processing_uses_material_languages_for_asr_segmentation_and_translation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    file_type: str,
):
    engine = _engine()
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    transcoded = tmp_path / "source.transcoded.mp4"
    captured: dict[str, object] = {}

    async def no_heartbeat(*_args, **_kwargs):
        return None

    async def fake_translate(sentences, *, source_language, target_language):
        captured["translation_source"] = source_language
        captured["translation_target"] = target_language
        captured["translation_sentences"] = list(sentences)
        return ["你好"]

    def fake_transcribe(scene, audio_path, *, word_timestamps, language):
        captured.update(
            {
                "scene": scene,
                "audio_path": audio_path,
                "word_timestamps": word_timestamps,
                "asr_language": language,
            }
        )
        return [{"start": 0.0, "end": 1.0, "text": "こんにちは。", "words": []}]

    def fake_segment(segments, *, language):
        captured["segmentation_language"] = language
        assert list(segments)[0]["text"] == "こんにちは。"
        return [{"source_text": "こんにちは。"}]

    def fake_audio_metadata(_audio, _material_id, _candidates, _duration):
        return [
            {
                "display_order": 1,
                "start_time": 0.0,
                "end_time": 1.0,
                "original_start_time": 0.0,
                "original_end_time": 1.0,
                "clip_audio_path": "clip.wav",
                "clip_duration": 1.0,
                "source_text": "こんにちは。",
            }
        ]

    monkeypatch.setattr(material_processing_service, "engine", engine)
    monkeypatch.setattr(material_processing_service, "_run_lock_heartbeat", no_heartbeat)
    def fake_transcode(_path):
        transcoded.write_bytes(b"video")
        return transcoded
    monkeypatch.setattr(material_processing_service, "transcode_video_for_storage", fake_transcode)
    monkeypatch.setattr(material_processing_service, "extract_audio", lambda path: path)
    monkeypatch.setattr(material_processing_service, "get_audio_duration", lambda _path: 1.0)
    monkeypatch.setattr(material_processing_service, "transcribe_for_scene", fake_transcribe)
    monkeypatch.setattr(material_processing_service, "segment_to_sentences", fake_segment)
    monkeypatch.setattr(material_processing_service, "build_sentence_audio_metadata", fake_audio_metadata)
    monkeypatch.setattr(material_processing_service, "translate_sentences", fake_translate)
    monkeypatch.setattr(material_processing_service, "_owns_processing_lock", lambda *_args: True)

    with Session(engine) as session:
        material = Material(
            title="Japanese",
            file_type=file_type,
            original_path=str(source),
            status="processing",
            processing_owner="job-1",
            content_language="ja",
            translation_language="zh-CN",
        )
        session.add(material)
        session.commit()
        material_id = material.id

    asyncio.run(material_processing_service._run_processing_pipeline(material_id, "job-1"))

    assert captured == {
        "scene": material_processing_service.MATERIAL_TRANSCRIPTION,
        "audio_path": str(transcoded if file_type == "video" else source),
        "word_timestamps": True,
        "asr_language": "ja",
        "segmentation_language": "ja",
        "translation_source": "ja",
        "translation_target": "zh-CN",
        "translation_sentences": ["こんにちは。"],
    }
    with Session(engine) as session:
        assert session.get(Material, material_id).status == "ready"
        assert session.get(Sentence, 1).translation == "你好"


def test_evaluation_job_uses_sentence_material_content_language(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    engine = _engine()
    recording_path = tmp_path / "recording.wav"
    recording_path.write_bytes(b"audio")
    captured: dict[str, object] = {}

    class StopAfterEvaluationHandoff(RuntimeError):
        pass

    def fake_evaluate(**kwargs):
        captured.update(kwargs)
        raise StopAfterEvaluationHandoff()

    monkeypatch.setattr(job_service, "engine", engine)
    monkeypatch.setattr(job_service, "extract_audio", lambda path: path)
    monkeypatch.setattr(job_service, "update_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(job_service, "evaluate_recording", fake_evaluate)

    with Session(engine) as session:
        material = Material(
            title="Korean",
            file_type="audio",
            original_path="source.wav",
            content_language="ko",
        )
        session.add(material)
        session.flush()
        sentence = Sentence(
            material_id=material.id,
            display_order=1,
            start_time=0.0,
            end_time=1.0,
            source_text="안녕하세요",
        )
        session.add(sentence)
        session.flush()
        recording = Recording(sentence_id=sentence.id, audio_path=str(recording_path))
        session.add(recording)
        session.commit()
        recording_id = recording.id

    with pytest.raises(StopAfterEvaluationHandoff):
        asyncio.run(job_service._run_evaluation("job-2", {"recording_id": recording_id}))

    assert captured["reference_text"] == "안녕하세요"
    assert captured["content_language"] == "ko"


def test_missing_translation_entries_stay_blank_instead_of_becoming_english_content():
    candidates = [{"source_text": "こんにちは。"}, {"source_text": "さようなら。"}]

    assert material_processing_service.normalize_translations(candidates, ["你好。"]) == [
        "你好。",
        "",
    ]
