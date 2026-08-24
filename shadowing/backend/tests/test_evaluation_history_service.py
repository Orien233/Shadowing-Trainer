from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.materials import router as materials_router
from app.core.database import get_session
from app.models.evaluation import Evaluation
from app.models.material import Material
from app.models.recording import Recording
from app.models.sentence import Sentence
from app.services.evaluation_history_service import list_latest_evaluations


def _score(recording_id: int, overall: int, created_at: datetime) -> Evaluation:
    return Evaluation(
        recording_id=recording_id,
        completeness_score=overall,
        fluency_score=overall,
        sync_score=overall,
        pronunciation_score=overall,
        overall_score=overall,
        feedback="",
        suggestion="",
        raw_metrics="{}",
        created_at=created_at,
    )


def test_latest_evaluations_are_derived_without_a_duplicate_score_table():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Material.__table__,
            Sentence.__table__,
            Recording.__table__,
            Evaluation.__table__,
        ],
    )
    now = datetime.now(UTC)

    with Session(engine) as session:
        material = Material(title="sample", file_type="audio", original_path="source.wav")
        session.add(material)
        session.flush()
        first = Sentence(
            material_id=material.id,
            display_order=1,
            start_time=0,
            end_time=1,
            source_text="First",
        )
        second = Sentence(
            material_id=material.id,
            display_order=2,
            start_time=1,
            end_time=2,
            source_text="Second",
        )
        session.add(first)
        session.add(second)
        session.flush()
        first_id = first.id
        second_id = second.id

        older = Recording(
            sentence_id=first.id,
            user_id="learner-a",
            audio_path="a-1.wav",
            duration=1.25,
        )
        latest = Recording(
            sentence_id=first.id,
            user_id="learner-a",
            audio_path="a-2.wav",
            duration=2.5,
        )
        other_sentence = Recording(
            sentence_id=second.id,
            user_id="learner-a",
            audio_path="a-3.wav",
            duration=3.75,
        )
        other_user = Recording(
            sentence_id=first.id,
            user_id="learner-b",
            audio_path="b-1.wav",
            duration=9.0,
        )
        session.add(older)
        session.add(latest)
        session.add(other_sentence)
        session.add(other_user)
        session.flush()

        session.add(_score(older.id, 60, now - timedelta(minutes=2)))
        session.add(_score(latest.id, 90, now - timedelta(minutes=1)))
        session.add(_score(other_sentence.id, 80, now))
        session.add(_score(other_user.id, 100, now))
        session.commit()

        rows = list_latest_evaluations(
            session=session,
            material_id=material.id,
            user_id="learner-a",
        )

        material_id = material.id

    assert [
        (row.sentence_id, row.evaluation.overall_score, row.recording_duration)
        for row in rows
    ] == [
        (first_id, 90, 2.5),
        (second_id, 80, 3.75),
    ]

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(materials_router)
    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        response = client.get(
            f"/api/materials/{material_id}/latest-evaluations",
            params={"user_id": "learner-a"},
        )

    assert response.status_code == 200
    assert [item["recording_duration"] for item in response.json()["evaluations"]] == [
        2.5,
        3.75,
    ]
