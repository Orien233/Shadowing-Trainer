from __future__ import annotations

from sqlmodel import Session, select

from app.models.evaluation import Evaluation
from app.models.material_sentence_score import MaterialSentenceScore

DEFAULT_USER_ID = "default"


def resolve_user_id(user_id: str | None) -> str:
    normalized = (user_id or "").strip()
    return normalized or DEFAULT_USER_ID


def record_material_sentence_score(
    *,
    session: Session,
    material_id: int,
    sentence_id: int,
    evaluation: Evaluation,
    recording_id: int | None,
    user_id: str | None = None,
) -> MaterialSentenceScore:
    snapshot = MaterialSentenceScore(
        user_id=resolve_user_id(user_id),
        material_id=material_id,
        sentence_id=sentence_id,
        main_db_recording_id=recording_id,
        main_db_evaluation_id=evaluation.id,
        completeness_score=evaluation.completeness_score,
        fluency_score=evaluation.fluency_score,
        sync_score=evaluation.sync_score,
        pronunciation_score=evaluation.pronunciation_score,
        overall_score=evaluation.overall_score,
        feedback=evaluation.feedback,
        suggestion=evaluation.suggestion,
        raw_metrics=evaluation.raw_metrics,
    )
    session.add(snapshot)
    return snapshot


def list_latest_scores_for_material(
    *,
    session: Session,
    material_id: int,
    user_id: str | None = None,
) -> list[MaterialSentenceScore]:
    normalized_user_id = resolve_user_id(user_id)
    statement = (
        select(MaterialSentenceScore)
        .where(MaterialSentenceScore.user_id == normalized_user_id)
        .where(MaterialSentenceScore.material_id == material_id)
        .order_by(
            MaterialSentenceScore.sentence_id.asc(),
            MaterialSentenceScore.created_at.desc(),
            MaterialSentenceScore.id.desc(),
        )
    )
    rows = session.exec(statement).all()

    latest_by_sentence: dict[int, MaterialSentenceScore] = {}
    for row in rows:
        if row.sentence_id in latest_by_sentence:
            continue
        latest_by_sentence[row.sentence_id] = row

    return [
        latest_by_sentence[sentence_id]
        for sentence_id in sorted(latest_by_sentence.keys())
    ]
