from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

from app.models.evaluation import Evaluation
from app.models.material_sentence_score import MaterialSentenceScore
from app.services.material_score_service import (
    delete_scores_for_material,
    get_latest_score_for_sentence,
    list_latest_scores_for_material,
    record_material_sentence_score,
    resolve_user_id,
)


def _build_evaluation(*, evaluation_id: int, recording_id: int, overall_score: int) -> Evaluation:
    return Evaluation(
        id=evaluation_id,
        recording_id=recording_id,
        completeness_score=max(overall_score - 3, 0),
        fluency_score=max(overall_score - 2, 0),
        sync_score=max(overall_score - 1, 0),
        pronunciation_score=overall_score,
        overall_score=overall_score,
        feedback=f"feedback-{overall_score}",
        suggestion=f"suggestion-{overall_score}",
        raw_metrics=f'{{"overall": {overall_score}}}',
    )


def _build_score_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(
        engine,
        tables=[MaterialSentenceScore.__table__],
    )
    return Session(engine)


def test_resolve_user_id_defaults_to_single_user() -> None:
    assert resolve_user_id(None) == "default"
    assert resolve_user_id("") == "default"
    assert resolve_user_id("   ") == "default"
    assert resolve_user_id(" user-a ") == "user-a"


def test_list_latest_scores_for_material_returns_latest_per_sentence() -> None:
    score_session = _build_score_session()
    try:
        first_eval = _build_evaluation(evaluation_id=1, recording_id=10, overall_score=70)
        second_eval = _build_evaluation(evaluation_id=2, recording_id=11, overall_score=85)
        third_eval = _build_evaluation(evaluation_id=3, recording_id=12, overall_score=78)

        record_material_sentence_score(
            score_session=score_session,
            material_id=100,
            sentence_id=1,
            evaluation=first_eval,
            recording_id=first_eval.recording_id,
            user_id="u1",
        )
        record_material_sentence_score(
            score_session=score_session,
            material_id=100,
            sentence_id=1,
            evaluation=second_eval,
            recording_id=second_eval.recording_id,
            user_id="u1",
        )
        record_material_sentence_score(
            score_session=score_session,
            material_id=100,
            sentence_id=2,
            evaluation=third_eval,
            recording_id=third_eval.recording_id,
            user_id="u1",
        )

        latest_rows = list_latest_scores_for_material(
            score_session=score_session,
            material_id=100,
            user_id="u1",
        )

        assert [item.sentence_id for item in latest_rows] == [1, 2]
        assert latest_rows[0].overall_score == 85
        assert latest_rows[1].overall_score == 78
    finally:
        score_session.close()


def test_get_latest_score_for_sentence_and_delete_material_scores() -> None:
    score_session = _build_score_session()
    try:
        first_eval = _build_evaluation(evaluation_id=4, recording_id=20, overall_score=66)
        second_eval = _build_evaluation(evaluation_id=5, recording_id=21, overall_score=91)

        record_material_sentence_score(
            score_session=score_session,
            material_id=200,
            sentence_id=8,
            evaluation=first_eval,
            recording_id=first_eval.recording_id,
            user_id="u2",
        )
        record_material_sentence_score(
            score_session=score_session,
            material_id=200,
            sentence_id=8,
            evaluation=second_eval,
            recording_id=second_eval.recording_id,
            user_id="u2",
        )

        latest_row = get_latest_score_for_sentence(
            score_session=score_session,
            material_id=200,
            sentence_id=8,
            user_id="u2",
        )
        assert latest_row is not None
        assert latest_row.overall_score == 91

        deleted_count = delete_scores_for_material(
            score_session=score_session,
            material_id=200,
        )
        assert deleted_count == 2

        after_delete = list_latest_scores_for_material(
            score_session=score_session,
            material_id=200,
            user_id="u2",
        )
        assert after_delete == []
    finally:
        score_session.close()
