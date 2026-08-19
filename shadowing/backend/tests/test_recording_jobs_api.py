from __future__ import annotations

import asyncio
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi import UploadFile
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.recordings import router as recordings_router
from app.core.database import get_session
from app.models.evaluation import Evaluation
from app.models.job import Job
from app.models.material import Material
from app.models.recording import Recording
from app.models.sentence import Sentence
from app.services.job_service import retry_job
from app.services.media_service import save_upload


@pytest.fixture()
def recording_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[TestClient, object]]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=[
        Material.__table__, Sentence.__table__, Recording.__table__, Evaluation.__table__,
        Job.__table__,
    ])
    media_path = tmp_path / "accepted.webm"

    async def fake_save_upload(*_args, **_kwargs):
        media_path.write_bytes(b"recording")
        return media_path

    monkeypatch.setattr("app.api.recordings.save_upload", fake_save_upload)
    monkeypatch.setattr("app.api.recordings.detect_file_type", lambda _path: "audio")
    monkeypatch.setattr("app.api.recordings.get_audio_duration", lambda _path: 2.0)

    with Session(engine) as session:
        material = Material(title="sample", file_type="audio", original_path="source.wav")
        session.add(material); session.flush()
        session.add(Sentence(material_id=material.id, display_order=1, start_time=0, end_time=1, source_text="Hello"))
        session.commit()

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app = FastAPI(); app.include_router(recordings_router)
    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client, engine


def test_recording_upload_returns_accepted_job(recording_client):
    client, engine = recording_client
    response = client.post(
        "/api/recordings/upload",
        data={"sentence_id": "1", "user_id": " learner-a "},
        files={"file": ("recording.webm", b"x", "audio/webm")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    with Session(engine) as session:
        recording = session.get(Recording, payload["recording_id"])
        job = session.get(Job, payload["job_id"])
        assert recording is not None and recording.status == "queued"
        assert recording.user_id == "learner-a"
        assert job is not None and job.kind == "evaluation" and job.status == "queued"


def test_cleanup_removes_recording_rows_and_evaluations(recording_client, tmp_path: Path):
    client, engine = recording_client
    audio_path = tmp_path / "finished.wav"; audio_path.write_bytes(b"audio")
    with Session(engine) as session:
        recording = Recording(sentence_id=1, audio_path=str(audio_path), status="completed")
        session.add(recording); session.flush()
        evaluation = Evaluation(recording_id=recording.id, completeness_score=1, fluency_score=1, sync_score=1, pronunciation_score=1, overall_score=1, feedback="", suggestion="", raw_metrics="{}")
        session.add(evaluation); session.flush()
        session.commit()

    response = client.delete("/api/recordings/cleanup")
    assert response.status_code == 200
    assert not audio_path.exists()
    with Session(engine) as session:
        assert session.exec(select(Recording)).all() == []
        assert session.exec(select(Evaluation)).all() == []


def test_failed_job_can_be_manually_requeued(recording_client):
    _client, engine = recording_client
    with Session(engine) as session:
        job = Job(kind="evaluation", status="failed", stage="failed", error_message="model unavailable")
        session.add(job); session.commit(); job_id = job.id
    with Session(engine) as session:
        retried = retry_job(session, job_id)
        assert retried.status == "queued"
        assert retried.progress == 0
        assert retried.error_message is None


def test_streaming_upload_removes_partial_file_when_byte_limit_is_exceeded(tmp_path: Path):
    upload = UploadFile(filename="too-large.webm", file=BytesIO(b"123456"))
    with pytest.raises(ValueError, match="allowed file size"):
        asyncio.run(save_upload(upload, tmp_path, max_bytes=5))
    assert list(tmp_path.iterdir()) == []
