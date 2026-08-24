import json
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.core.config import settings
from app.core.database import get_session
from app.models.evaluation import Evaluation
from app.models.job import Job
from app.models.recording import Recording
from app.models.sentence import Sentence
from app.schemas.recording import RecordingUploadResponse
from app.schemas.system import RecordingCleanupResponse
from app.services.evaluation_history_service import normalize_user_id
from app.services.job_service import enqueue_job
from app.services.media_service import detect_file_type, get_audio_duration, save_upload

router = APIRouter(prefix="/api/recordings", tags=["recordings"])

_AUDIO_MEDIA_TYPES = {
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".oga": "audio/ogg",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".wav": "audio/wav",
    ".wave": "audio/wav",
    ".webm": "audio/webm",
}


def _recording_media_type(audio_path: Path) -> str:
    return _AUDIO_MEDIA_TYPES.get(
        audio_path.suffix.lower(),
        mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream",
    )


@router.delete("/cleanup", response_model=RecordingCleanupResponse)
def cleanup_recordings(session: Session = Depends(get_session)):
    """Delete recording rows and files together so history never points to nothing."""
    recordings = list(session.exec(select(Recording)).all())
    recording_ids = [item.id for item in recordings if item.id is not None]
    paths = [Path(item.audio_path) for item in recordings]
    if recording_ids:
        evaluations = session.exec(select(Evaluation).where(Evaluation.recording_id.in_(recording_ids))).all()
        for evaluation in evaluations:
            session.delete(evaluation)
    for job in session.exec(select(Job).where(Job.kind == "evaluation")).all():
        try:
            if int(json.loads(job.payload).get("recording_id", -1)) in recording_ids:
                job.status = "cancelled"
                job.stage = "cancelled"
                session.add(job)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    for recording in recordings:
        session.delete(recording)
    session.commit()

    failed_files = []
    deleted_files = 0
    for path in paths:
        try:
            path.unlink(missing_ok=True)
            deleted_files += 1
        except OSError as exc:
            failed_files.append({"path": str(path), "reason": str(exc)})
    if failed_files:
        enqueue_job(session, "storage_cleanup", {"paths": [item["path"] for item in failed_files]})
        session.commit()
    return RecordingCleanupResponse(
        target_dir=str(settings.recordings_dir), total_files=len(paths),
        deleted_files=deleted_files, failed_files=failed_files,
    )


@router.post("/upload", response_model=RecordingUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_recording(
    sentence_id: int = Form(...),
    file: UploadFile = File(...),
    user_id: str | None = Form(default=None),
    session: Session = Depends(get_session),
):
    sentence = session.get(Sentence, sentence_id)
    if not sentence:
        raise HTTPException(status_code=404, detail="Sentence not found.")
    try:
        saved_path = await save_upload(file, settings.recordings_dir, max_bytes=settings.recording_max_bytes)
        if detect_file_type(saved_path) != "audio":
            raise ValueError("Recording must contain an audio stream.")
        if get_audio_duration(saved_path) > settings.recording_max_duration_seconds:
            raise ValueError(f"Recording cannot exceed {settings.recording_max_duration_seconds:.0f} seconds.")
    except ValueError as exc:
        if "saved_path" in locals():
            saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=str(exc))
    except Exception as exc:
        if "saved_path" in locals():
            saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Invalid recording media: {exc}")

    recording = Recording(
        sentence_id=sentence_id,
        user_id=normalize_user_id(user_id),
        audio_path=str(saved_path),
        status="queued",
    )
    session.add(recording)
    session.flush()
    job = enqueue_job(session, "evaluation", {"recording_id": recording.id})
    recording.job_id = job.id
    session.add(recording)
    session.commit()
    return RecordingUploadResponse(recording_id=recording.id, job_id=job.id, status="queued")


@router.get("/{recording_id}/audio")
def get_recording_audio(recording_id: int, session: Session = Depends(get_session)):
    recording = session.get(Recording, recording_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found.")

    audio_path = Path(recording.audio_path)
    if not audio_path.exists() or not audio_path.is_file():
        raise HTTPException(status_code=404, detail="Recording audio file not found.")

    return FileResponse(audio_path, media_type=_recording_media_type(audio_path))
