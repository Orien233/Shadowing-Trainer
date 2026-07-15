import asyncio
import json
import logging
import mimetypes
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc, update
from sqlmodel import Session, func, select

from app.core.config import settings
from app.core.database import engine, get_session
from app.models.evaluation import Evaluation
from app.models.job import Job
from app.models.material_sentence_score import MaterialSentenceScore
from app.models.material import Material
from app.models.recording import Recording
from app.models.sentence import Sentence
from app.schemas.material import MaterialDetail, MaterialRead
from app.schemas.material_score import (
    MaterialLatestEvaluationsRead,
    SentenceLatestEvaluationRead,
)
from app.services.material_score_service import (
    DEFAULT_USER_ID,
    list_latest_scores_for_material,
    resolve_user_id,
)
from app.services.media_service import (
    build_sentence_audio_metadata,
    detect_file_type,
    extract_audio,
    get_audio_duration,
    save_upload,
    transcode_video_for_storage,
)
from app.services.job_service import enqueue_job, update_job
from app.services.segmentation_service import segment_to_sentences
from app.services.transcription_service import transcribe_audio_with_word_timestamps
from app.services.translation_service import translate_sentences

router = APIRouter(prefix="/api/materials", tags=["materials"])
logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _clear_processing_lock_fields(material: Material) -> None:
    material.processing_owner = None
    material.processing_started_at = None
    material.processing_heartbeat_at = None


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


def _get_rowcount(result: object) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


def _touch_processing_lock(material_id: int, owner: str) -> bool:
    statement = (
        update(Material)
        .where(Material.id == material_id)
        .where(Material.status == "processing")
        .where(Material.processing_owner == owner)
        .values(processing_heartbeat_at=_now_utc())
    )
    with Session(engine) as heartbeat_session:
        result = heartbeat_session.exec(statement)
        updated_rows = _get_rowcount(result)
        if updated_rows < 1:
            heartbeat_session.rollback()
            return False
        heartbeat_session.commit()
        return True


def _owns_processing_lock(material_id: int, owner: str) -> bool:
    with Session(engine) as lock_session:
        material = lock_session.get(Material, material_id)
        if not material:
            return False
        return material.status == "processing" and material.processing_owner == owner


async def _run_lock_heartbeat(material_id: int, owner: str, stop_event: asyncio.Event) -> None:
    interval = max(settings.processing_lock_heartbeat_seconds, 1)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            pass

        heartbeat_ok = await asyncio.to_thread(_touch_processing_lock, material_id, owner)
        if heartbeat_ok:
            continue

        logger.warning(
            "Lost processing lock heartbeat for material %s owned by %s.",
            material_id,
            owner,
        )
        stop_event.set()
        return


# Ensure necessary directories exist at startup
@router.post("/upload", response_model=MaterialRead)
async def upload_material(
    title: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
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

    normalized_user_id = resolve_user_id(user_id)
    latest_by_sentence: dict[int, SentenceLatestEvaluationRead] = {}

    score_rows = list_latest_scores_for_material(
        session=session,
        material_id=material_id,
        user_id=normalized_user_id,
    )
    for score_row in score_rows:
        latest_by_sentence[score_row.sentence_id] = _build_latest_evaluation_read(
            sentence_id=score_row.sentence_id,
            main_db_recording_id=score_row.main_db_recording_id,
            main_db_evaluation_id=score_row.main_db_evaluation_id,
            completeness_score=score_row.completeness_score,
            fluency_score=score_row.fluency_score,
            sync_score=score_row.sync_score,
            pronunciation_score=score_row.pronunciation_score,
            overall_score=score_row.overall_score,
            feedback=score_row.feedback,
            suggestion=score_row.suggestion,
            raw_metrics=score_row.raw_metrics,
            created_at=score_row.created_at,
        )

    fallback_rows: list[SentenceLatestEvaluationRead] = []
    if normalized_user_id == DEFAULT_USER_ID:
        fallback_rows = _list_latest_scores_from_main_db(session, material_id)
    for fallback_row in fallback_rows:
        if fallback_row.sentence_id in latest_by_sentence:
            continue
        latest_by_sentence[fallback_row.sentence_id] = fallback_row

    evaluations = [
        latest_by_sentence[sentence_id]
        for sentence_id in sorted(latest_by_sentence.keys())
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
    main_db_recording_id: int | None,
    main_db_evaluation_id: int | None,
    completeness_score: int,
    fluency_score: int,
    sync_score: int,
    pronunciation_score: int,
    overall_score: int,
    feedback: str,
    suggestion: str,
    raw_metrics: str,
    created_at: datetime,
) -> SentenceLatestEvaluationRead:
    return SentenceLatestEvaluationRead(
        sentence_id=sentence_id,
        main_db_recording_id=main_db_recording_id,
        main_db_evaluation_id=main_db_evaluation_id,
        completeness_score=completeness_score,
        fluency_score=fluency_score,
        sync_score=sync_score,
        pronunciation_score=pronunciation_score,
        overall_score=overall_score,
        feedback=feedback,
        suggestion=suggestion,
        raw_metrics=raw_metrics,
        word_alignment=_extract_word_alignment(raw_metrics),
        created_at=created_at,
    )


def _extract_word_alignment(raw_metrics: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw_metrics)
    except Exception:
        return None

    word_alignment = payload.get("word_alignment")
    if isinstance(word_alignment, dict):
        return word_alignment
    return None


def _normalize_translations_for_sentences(
    sentence_candidates: list[dict[str, object]],
    translations: list[str],
) -> list[str]:
    expected_count = len(sentence_candidates)
    normalized = list(translations[:expected_count])
    if len(normalized) == expected_count:
        return normalized

    for item in sentence_candidates[len(normalized) :]:
        source_text = str(item.get("source_text") or "").strip()
        if source_text:
            normalized.append(f"[Translation unavailable] {source_text}")
        else:
            normalized.append("[Translation unavailable]")
    return normalized


def _list_latest_scores_from_main_db(
    session: Session,
    material_id: int,
) -> list[SentenceLatestEvaluationRead]:
    statement = (
        select(Sentence.id, Recording.id, Evaluation)
        .join(Recording, Recording.sentence_id == Sentence.id)
        .join(Evaluation, Evaluation.recording_id == Recording.id)
        .where(Sentence.material_id == material_id)
        .order_by(
            Sentence.id.asc(),
            Evaluation.created_at.desc(),
            Evaluation.id.desc(),
        )
    )
    rows = session.exec(statement).all()

    latest_by_sentence: dict[int, SentenceLatestEvaluationRead] = {}
    for sentence_id, recording_id, evaluation in rows:
        if sentence_id in latest_by_sentence:
            continue
        latest_by_sentence[sentence_id] = _build_latest_evaluation_read(
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
            created_at=evaluation.created_at,
        )

    return [
        latest_by_sentence[sentence_id]
        for sentence_id in sorted(latest_by_sentence.keys())
    ]


def _mark_material_failed(material_id: int, owner: str | None = None, error_message: str | None = None) -> None:
    with Session(engine) as failure_session:
        material = failure_session.get(Material, material_id)
        if not material:
            return

        if owner is not None:
            lock_owned = material.status == "processing" and material.processing_owner == owner
            if not lock_owned:
                return

        material.status = "failed"
        material.processing_stage = "failed"
        material.error_message = error_message
        _clear_processing_lock_fields(material)
        failure_session.add(material)
        failure_session.commit()


# Extract the 'content' field from the LLM API response, handling different possible response formats.
async def _process_material_in_background(material_id: int, owner: str) -> None:
    heartbeat_stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _run_lock_heartbeat(material_id, owner, heartbeat_stop_event)
    )
    try:
        with Session(engine) as session:
            material = session.get(Material, material_id)
            if not material:
                return
            if material.status != "processing" or material.processing_owner != owner:
                logger.warning(
                    "Skipping material %s: processing lock is not owned by current worker.",
                    material_id,
                )
                return
            source_path = Path(material.original_path)
            is_video = material.file_type == "video"
            audio_source_path = source_path
            if is_video:
                audio_source_path = await asyncio.to_thread(transcode_video_for_storage, source_path)
                source_path.unlink(missing_ok=True)
                material.original_path = str(audio_source_path)
                material.processing_stage = "extracting_audio"
                material.processing_progress = 20
                session.add(material)
                session.commit()

        audio_path = await asyncio.to_thread(extract_audio, audio_source_path)
        duration_probe_path = audio_source_path if is_video else audio_path
        duration = await asyncio.to_thread(get_audio_duration, duration_probe_path)
        segments = await asyncio.to_thread(transcribe_audio_with_word_timestamps, str(audio_path))
        sentence_candidates = await asyncio.to_thread(segment_to_sentences, segments)
        enriched_candidates, translations = await asyncio.gather(
            asyncio.to_thread(
                build_sentence_audio_metadata,
                audio_path,
                material_id,
                sentence_candidates,
                duration,
            ),
            translate_sentences(item["source_text"] for item in sentence_candidates),
        )
        if len(enriched_candidates) != len(sentence_candidates):
            raise RuntimeError(
                "Sentence metadata count mismatch: "
                f"expected={len(sentence_candidates)} got={len(enriched_candidates)}"
            )
        if len(translations) != len(enriched_candidates):
            logger.warning(
                "Translation count mismatch for material %s: expected=%s got=%s. "
                "Missing translations will be filled with fallback text.",
                material_id,
                len(enriched_candidates),
                len(translations),
            )
        normalized_translations = _normalize_translations_for_sentences(
            enriched_candidates,
            translations,
        )

        still_owns_lock = await asyncio.to_thread(_owns_processing_lock, material_id, owner)
        if not still_owns_lock:
            logger.warning(
                "Material %s processing aborted because lock ownership was lost before DB write.",
                material_id,
            )
            return

        with Session(engine) as session:
            material = session.get(Material, material_id)
            if not material:
                return
            if material.status != "processing" or material.processing_owner != owner:
                logger.warning(
                    "Material %s processing aborted: lock owner changed before commit.",
                    material_id,
                )
                return

            existing_sentences = session.exec(
                select(Sentence).where(Sentence.material_id == material_id)
            ).all()
            for existing in existing_sentences:
                session.delete(existing)
            session.commit()

            for item, translation in zip(enriched_candidates, normalized_translations):
                sentence = Sentence(
                    material_id=material_id,
                    display_order=item["display_order"],
                    start_time=item["start_time"],
                    end_time=item["end_time"],
                    original_start_time=item["original_start_time"],
                    original_end_time=item["original_end_time"],
                    clip_audio_path=item["clip_audio_path"],
                    clip_duration=item["clip_duration"],
                    source_text=item["source_text"],
                    translation=translation,
                )
                session.add(sentence)

            material.audio_path = str(audio_path)
            material.duration = duration
            material.status = "ready"
            material.processing_stage = "completed"
            material.processing_progress = 100
            material.error_message = None
            _clear_processing_lock_fields(material)
            session.add(material)
            session.commit()
    except Exception as exc:
        logger.exception("Failed processing material %s", material_id)
        await asyncio.to_thread(_mark_material_failed, material_id, owner, str(exc)[:2000])
    finally:
        heartbeat_stop_event.set()
        try:
            await heartbeat_task
        except Exception:
            logger.exception("Heartbeat task failed for material %s", material_id)


async def process_material_job(material_id: int, job_id: str) -> None:
    """Worker entrypoint; API routes only enqueue this operation."""
    with Session(engine) as session:
        material = session.get(Material, material_id)
        if not material:
            raise RuntimeError("Material no longer exists.")
        material.status = "processing"
        material.processing_owner = job_id
        material.processing_started_at = _now_utc()
        material.processing_heartbeat_at = _now_utc()
        material.processing_stage = "transcribing"
        material.processing_progress = 15
        material.error_message = None
        session.add(material)
        session.commit()
    update_job(job_id, stage="transcribing_material", progress=25)
    await _process_material_in_background(material_id, job_id)
    with Session(engine) as session:
        material = session.get(Material, material_id)
        if not material or material.status != "ready":
            raise RuntimeError(material.error_message if material else "Material processing failed.")
    update_job(job_id, stage="material_ready", progress=95)


# This endpoint triggers the processing of the material: extracting audio, transcribing, segmenting, translating, and saving sentences.
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

    for snapshot in session.exec(
        select(MaterialSentenceScore).where(MaterialSentenceScore.material_id == material_id)
    ).all():
        session.delete(snapshot)

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
