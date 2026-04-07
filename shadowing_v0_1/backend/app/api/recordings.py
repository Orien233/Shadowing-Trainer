from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from app.core.config import settings
from app.core.database import get_session
from app.models.evaluation import Evaluation
from app.models.recording import Recording
from app.models.sentence import Sentence
from app.schemas.recording import RecordingUploadResponse
from app.schemas.system import RecordingCleanupResponse
from app.services.evaluation_service import evaluate_recording
from app.services.media_service import extract_audio, save_upload
from app.services.recording_file_service import cleanup_recording_files

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


@router.delete("/cleanup", response_model=RecordingCleanupResponse)
def cleanup_recordings():
    return cleanup_recording_files()


@router.post("/upload", response_model=RecordingUploadResponse)
async def upload_recording(
    sentence_id: int = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    sentence = session.get(Sentence, sentence_id)
    if not sentence:
        raise HTTPException(status_code=404, detail="Sentence not found.")

    saved_path = await save_upload(file, settings.recordings_dir)
    normalized_path = extract_audio(saved_path)

    result = evaluate_recording(
        reference_text=sentence.source_text,
        reference_duration=max(sentence.end_time - sentence.start_time, 0.1),
        recording_path=str(normalized_path),
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

    return RecordingUploadResponse(recording_id=recording.id, evaluation=evaluation)
