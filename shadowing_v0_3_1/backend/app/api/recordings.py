import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from app.core.config import settings
from app.core.database import get_session
from app.core.score_database import get_score_session
from app.models.evaluation import Evaluation
from app.models.recording import Recording
from app.models.sentence import Sentence
from app.schemas.recording import RecordingUploadResponse
from app.schemas.system import RecordingCleanupResponse
from app.services.evaluation_service import evaluate_recording
from app.services.media_service import extract_audio, save_upload
from app.services.material_score_service import record_material_sentence_score
from app.services.recording_file_service import cleanup_recording_files

router = APIRouter(prefix="/api/recordings", tags=["recordings"])
logger = logging.getLogger(__name__)


@router.delete("/cleanup", response_model=RecordingCleanupResponse)
def cleanup_recordings():
    return cleanup_recording_files()


@router.post("/upload", response_model=RecordingUploadResponse)
async def upload_recording(
    sentence_id: int = Form(...),
    file: UploadFile = File(...),
    user_id: str | None = Form(default=None),
    session: Session = Depends(get_session),
    score_session: Session = Depends(get_score_session),
):
    sentence = session.get(Sentence, sentence_id)
    if not sentence:
        raise HTTPException(status_code=404, detail="Sentence not found.")

    saved_path = await save_upload(file, settings.recordings_dir)
    normalized_path = extract_audio(saved_path)

    result = evaluate_recording(
        reference_text=sentence.source_text,
        reference_duration=max(
            sentence.clip_duration
            if sentence.clip_duration is not None
            else sentence.end_time - sentence.start_time,
            0.1,
        ),
        recording_path=str(normalized_path),
        reference_audio_path=sentence.clip_audio_path,
    )

    recording = Recording(
        sentence_id=sentence_id,
        audio_path=str(normalized_path),
        duration=result["duration"],
        asr_text=result["asr_text"],
    )
    session.add(recording)
    session.commit()
    session.refresh(recording)

    evaluation = Evaluation(
        recording_id=recording.id,
        completeness_score=result["completeness_score"],
        fluency_score=result["fluency_score"],
        sync_score=result["sync_score"],
        pronunciation_score=result["pronunciation_score"],
        overall_score=result["overall_score"],
        feedback=result["feedback"],
        suggestion=result["suggestion"],
        raw_metrics=result["raw_metrics"],
    )
    session.add(evaluation)
    session.commit()
    session.refresh(evaluation)

    try:
        record_material_sentence_score(
            score_session=score_session,
            material_id=sentence.material_id,
            sentence_id=sentence_id,
            evaluation=evaluation,
            recording_id=recording.id,
            user_id=user_id,
        )
    except Exception:
        logger.exception(
            "Failed writing score snapshot for sentence %s in material %s",
            sentence_id,
            sentence.material_id,
        )

    return RecordingUploadResponse(recording_id=recording.id, evaluation=evaluation)
