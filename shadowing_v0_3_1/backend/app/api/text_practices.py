from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.text_practice import TextPractice
from app.schemas.text_practice import TextGenerationRequest, TextPracticeCreate, TextPracticeRead, TextPracticeUpdate, TTSJobResponse, TTSOptions
from app.services.text_generation_service import create_generated_practice, create_imported_practice, json_words, update_practice
from app.services.tts_service import queue_tts

router = APIRouter(prefix="/api/text-practices", tags=["text-practices"])


def _read(item: TextPractice) -> TextPracticeRead:
    return TextPracticeRead.model_validate({**item.model_dump(), "requested_words": json_words(item.requested_words_json), "used_words": json_words(item.used_words_json), "unused_words": json_words(item.unused_words_json)})


@router.get("", response_model=list[TextPracticeRead])
def list_text_practices(session: Session = Depends(get_session)):
    return [_read(item) for item in session.exec(select(TextPractice).order_by(TextPractice.created_at.desc())).all()]


@router.post("/generate", response_model=TextPracticeRead, status_code=201)
def generate_text_practice(payload: TextGenerationRequest, session: Session = Depends(get_session)):
    try:
        return _read(create_generated_practice(session, payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Text generation failed: {str(exc)[:400]}") from exc


@router.post("/import", response_model=TextPracticeRead, status_code=201)
def import_text_practice(payload: TextPracticeCreate, session: Session = Depends(get_session)):
    return _read(create_imported_practice(session, payload))


@router.patch("/{practice_id}", response_model=TextPracticeRead)
def edit_text_practice(practice_id: int, payload: TextPracticeUpdate, session: Session = Depends(get_session)):
    practice = session.get(TextPractice, practice_id)
    if not practice:
        raise HTTPException(status_code=404, detail="Text practice not found.")
    return _read(update_practice(session, practice, title=payload.title, body=payload.body))


@router.post("/{practice_id}/tts", response_model=TTSJobResponse, status_code=202)
def synthesize_text_practice(practice_id: int, payload: TTSOptions, session: Session = Depends(get_session)):
    practice = session.get(TextPractice, practice_id)
    if not practice:
        raise HTTPException(status_code=404, detail="Text practice not found.")
    try:
        job = queue_tts(session, practice, payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TTSJobResponse(text_practice_id=practice_id, job_id=job.id, status="queued")
