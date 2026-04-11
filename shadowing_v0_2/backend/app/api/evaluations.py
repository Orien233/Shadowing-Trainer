from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.database import get_session
from app.models.evaluation import Evaluation
from app.schemas.evaluation import EvaluationRead

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


@router.get("/{evaluation_id}", response_model=EvaluationRead)
def get_evaluation(evaluation_id: int, session: Session = Depends(get_session)):
    evaluation = session.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    return evaluation
