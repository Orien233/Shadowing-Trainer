import logging
import mimetypes
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc
from sqlmodel import Session, func, select

from app.core.config import settings
from app.core.database import get_session
from app.models.evaluation import Evaluation
from app.models.job import Job
from app.models.material import Material
from app.models.recording import Recording
from app.models.sentence import Sentence
from app.schemas.material import MaterialDetail, MaterialRead
from app.schemas.evaluation_history import (
    MaterialLatestEvaluationsRead,
    SentenceLatestEvaluationRead,
)
from app.services.evaluation_history_service import (
    list_latest_evaluations,
    normalize_user_id,
)
from app.services.media_service import (
    detect_file_type,
    save_upload,
)
from app.services.job_service import enqueue_job
from app.services.language_catalog import LanguageValidationError, normalize_language_tag

router = APIRouter(prefix="/api/materials", tags=["materials"])
logger = logging.getLogger(__name__)


def _is_within_data_dir(path: Path) -> bool:
    try:
        path.resolve().relative_to(settings.data_path.resolve())
        return True
    except Exception:
        return False


def _safe_delete_file(path: Path) -> bool:
    if not _is_within_data_dir(path):
        logger.warning("Skip deleting file outside data directory: %s", path)
        return False

    if not path.exists() or not path.is_file():
        return True

    try:
        path.unlink()
        return True
    except Exception:
        logger.exception("Failed deleting file: %s", path)
        return False


def _safe_delete_directory(path: Path) -> bool:
    if not _is_within_data_dir(path):
        logger.warning("Skip deleting directory outside data directory: %s", path)
        return False

    if not path.exists() or not path.is_dir():
        return True

    try:
        shutil.rmtree(path)
        return True
    except Exception:
        logger.exception("Failed deleting directory: %s", path)
        return False


def _recording_artifact_paths(recording_audio_path: str) -> set[Path]:
    artifacts = {Path(recording_audio_path)}
    stem = Path(recording_audio_path).stem
    for candidate in settings.recordings_dir.glob(f"{stem}.*"):
        artifacts.add(candidate)
    return artifacts


@router.post("/upload", response_model=MaterialRead)
async def upload_material(
    title: str = Form(...),
    content_language: str = Form(default="en"),
    translation_language: str = Form(default="zh-CN"),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    try:
        normalized_content_language = normalize_language_tag(content_language)
        normalized_translation_language = normalize_language_tag(translation_language)
    except LanguageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        original_path = await save_upload(file, settings.materials_dir)
        file_type = detect_file_type(original_path)
        if file_type == "unknown":
            raise ValueError("Unsupported file type.")
    except ValueError as exc:
        if "original_path" in locals():
            original_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc))

    material = Material(
        title=title,
        file_type=file_type,
        original_path=str(original_path),
        status="queued",
        content_language=normalized_content_language,
        translation_language=normalized_translation_language,
    )
    session.add(material)
    session.commit()
    session.refresh(material)
    if material.id is None:
        raise HTTPException(status_code=500, detail="Material creation failed.")

    job = enqueue_job(session, "material_processing", {"material_id": material.id})
    material.job_id = job.id
    material.processing_stage = "queued"
    session.add(material)
    session.commit()
    session.refresh(material)
    return material


# For testing purposes, you can also add a simple endpoint to list all materials and get details of a specific material.
@router.get("", response_model=list[MaterialRead])
def list_materials(session: Session = Depends(get_session)):
    statement = select(Material).order_by(desc(getattr(Material, "created_at")))
    return list(session.exec(statement).all())


# Get material details along with the count of sentences (if processed)
@router.get("/{material_id}", response_model=MaterialDetail)
def get_material(material_id: int, session: Session = Depends(get_session)):
    material = session.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")

    return _build_material_detail(session, material)


@router.get(
    "/{material_id}/latest-evaluations",
    response_model=MaterialLatestEvaluationsRead,
)
def get_material_latest_evaluations(
    material_id: int,
    user_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    material = session.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")

    normalized_user_id = normalize_user_id(user_id)
    latest_rows = list_latest_evaluations(
        session=session,
        material_id=material_id,
        user_id=normalized_user_id,
    )
    evaluations = [
        _build_latest_evaluation_read(
            sentence_id=row.sentence_id,
            recording_id=row.recording_id,
            recording_duration=row.recording_duration,
            evaluation=row.evaluation,
        )
        for row in latest_rows
    ]
    return MaterialLatestEvaluationsRead(
        material_id=material_id,
        user_id=normalized_user_id,
        evaluations=evaluations,
    )


def _build_material_detail(session: Session, material: Material) -> MaterialDetail:
    sentence_count = session.exec(
        select(func.count()).select_from(Sentence).where(Sentence.material_id == material.id)
    ).one()
    return MaterialDetail(**material.model_dump(), sentence_count=sentence_count)


def _build_latest_evaluation_read(
    *,
    sentence_id: int,
    recording_id: int,
    recording_duration: float | None,
    evaluation: Evaluation,
) -> SentenceLatestEvaluationRead:
    return SentenceLatestEvaluationRead(
        sentence_id=sentence_id,
        recording_id=recording_id,
        recording_duration=recording_duration,
        evaluation_id=evaluation.id,
        completeness_score=evaluation.completeness_score,
        fluency_score=evaluation.fluency_score,
        sync_score=evaluation.sync_score,
        pronunciation_score=evaluation.pronunciation_score,
        overall_score=evaluation.overall_score,
        feedback=evaluation.feedback,
        suggestion=evaluation.suggestion,
        raw_metrics=evaluation.raw_metrics,
        word_alignment=evaluation.word_alignment,
        created_at=evaluation.created_at,
    )


@router.post("/{material_id}/process", response_model=MaterialDetail)
async def process_material(material_id: int, session: Session = Depends(get_session)):
    material = session.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")

    current_job = session.get(Job, material.job_id) if material.job_id else None
    if current_job and current_job.status in {"queued", "running"}:
        return _build_material_detail(session, material)
    job = enqueue_job(session, "material_processing", {"material_id": material_id})
    material.status = "queued"
    material.job_id = job.id
    material.processing_stage = "queued"
    material.processing_progress = 0
    material.error_message = None
    session.add(material)
    session.commit()
    session.refresh(material)
    return _build_material_detail(session, material)


@router.delete("/{material_id}", status_code=204)
async def delete_material(
    material_id: int,
    session: Session = Depends(get_session),
):
    material = session.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")

    if material.job_id:
        queued_job = session.get(Job, material.job_id)
        if queued_job and queued_job.status in {"queued", "running"}:
            queued_job.status = "cancelled"
            queued_job.stage = "cancelled"
            session.add(queued_job)

    sentences = session.exec(
        select(Sentence).where(Sentence.material_id == material_id)
    ).all()
    sentence_ids = [sentence.id for sentence in sentences if sentence.id is not None]

    recordings: list[Recording] = []
    if sentence_ids:
        sentence_id_col = getattr(Recording, "sentence_id")
        recordings = session.exec(
            select(Recording).where(sentence_id_col.in_(sentence_ids))
        ).all()
    recording_ids = [recording.id for recording in recordings if recording.id is not None]

    evaluations: list[Evaluation] = []
    if recording_ids:
        recording_id_col = getattr(Evaluation, "recording_id")
        evaluations = session.exec(
            select(Evaluation).where(recording_id_col.in_(recording_ids))
        ).all()

    file_paths: set[Path] = set()
    directory_paths: set[Path] = {settings.sentence_audio_dir / f"material_{material_id}"}

    file_paths.add(Path(material.original_path))
    if material.file_type == "video":
        file_paths.add(Path(material.original_path))
    file_paths.add(settings.audio_dir / f"{Path(material.original_path).stem}.wav")
    if material.audio_path:
        file_paths.add(Path(material.audio_path))

    for sentence in sentences:
        if sentence.clip_audio_path:
            file_paths.add(Path(sentence.clip_audio_path))

    for evaluation in evaluations:
        session.delete(evaluation)

    for recording in recordings:
        for artifact in _recording_artifact_paths(recording.audio_path):
            file_paths.add(artifact)
        session.delete(recording)

    for sentence in sentences:
        session.delete(sentence)

    session.delete(material)
    session.commit()

    pending_cleanup = [str(path) for path in directory_paths if not _safe_delete_directory(path)]
    pending_cleanup.extend(str(path) for path in file_paths if not _safe_delete_file(path))
    if pending_cleanup:
        enqueue_job(session, "storage_cleanup", {"paths": pending_cleanup})
        session.commit()

    return Response(status_code=204)


@router.get("/{material_id}/audio")
def get_material_audio(material_id: int, session: Session = Depends(get_session)):
    material = session.get(Material, material_id)
    if not material or not material.audio_path:
        raise HTTPException(status_code=404, detail="Audio not found.")
    audio_path = Path(material.audio_path)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found.")
    return FileResponse(audio_path, media_type="audio/wav")


@router.get("/{material_id}/video")
def get_material_video(material_id: int, session: Session = Depends(get_session)):
    material = session.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")
    if material.file_type != "video":
        raise HTTPException(status_code=400, detail="Material is not a video.")

    source_path = Path(material.original_path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found.")

    mime_type, _ = mimetypes.guess_type(str(source_path))
    return FileResponse(source_path, media_type=mime_type or "video/mp4")
