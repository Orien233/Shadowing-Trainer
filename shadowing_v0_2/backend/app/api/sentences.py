from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.material import Material
from app.models.sentence import Sentence
from app.schemas.sentence import SentenceRead

router = APIRouter(prefix="/api/materials", tags=["sentences"])


@router.get("/{material_id}/sentences", response_model=list[SentenceRead])
def get_sentences(material_id: int, session: Session = Depends(get_session)):
    material = session.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")

    statement = (
        select(Sentence)
        .where(Sentence.material_id == material_id)
        .order_by(Sentence.display_order.asc())
    )
    return list(session.exec(statement).all())
