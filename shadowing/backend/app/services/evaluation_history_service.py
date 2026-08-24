from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from app.models.evaluation import Evaluation
from app.models.recording import Recording
from app.models.sentence import Sentence

DEFAULT_USER_ID = "default"


@dataclass(frozen=True, slots=True)
class LatestSentenceEvaluation:
    sentence_id: int
    recording_id: int
    recording_duration: float | None
    evaluation: Evaluation


def normalize_user_id(user_id: str | None) -> str:
    normalized = (user_id or "").strip()
    return normalized or DEFAULT_USER_ID


def list_latest_evaluations(
    *,
    session: Session,
    material_id: int,
    user_id: str | None = None,
) -> list[LatestSentenceEvaluation]:
    """Return one latest evaluation per sentence for a material and user."""
    statement = (
        select(Sentence.id, Recording.id, Recording.duration, Evaluation)
        .join(Recording, Recording.sentence_id == Sentence.id)
        .join(Evaluation, Evaluation.recording_id == Recording.id)
        .where(Sentence.material_id == material_id)
        .where(Recording.user_id == normalize_user_id(user_id))
        .order_by(
            Sentence.id.asc(),
            Evaluation.created_at.desc(),
            Evaluation.id.desc(),
        )
    )
    rows = session.exec(statement).all()

    latest_by_sentence: dict[int, LatestSentenceEvaluation] = {}
    for sentence_id, recording_id, recording_duration, evaluation in rows:
        if sentence_id in latest_by_sentence:
            continue
        latest_by_sentence[sentence_id] = LatestSentenceEvaluation(
            sentence_id=sentence_id,
            recording_id=recording_id,
            recording_duration=recording_duration,
            evaluation=evaluation,
        )

    return [latest_by_sentence[key] for key in sorted(latest_by_sentence)]
