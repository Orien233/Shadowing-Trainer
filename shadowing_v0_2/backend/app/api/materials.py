import asyncio
import logging
import mimetypes
import os
import socket
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import and_, desc, or_, update
from sqlmodel import Session, func, select

from app.core.config import settings
from app.core.database import engine, get_session
from app.models.material import Material
from app.models.sentence import Sentence
from app.schemas.material import MaterialDetail, MaterialRead
from app.services.media_service import (
    build_sentence_audio_metadata,
    detect_file_type,
    extract_audio,
    get_audio_duration,
    save_upload,
)
from app.services.segmentation_service import segment_to_sentences
from app.services.transcription_service import transcribe_audio
from app.services.translation_service import translate_sentences

router = APIRouter(prefix="/api/materials", tags=["materials"])
logger = logging.getLogger(__name__)
processing_tasks: dict[int, asyncio.Task[None]] = {}
WORKER_INSTANCE_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _now_utc() -> datetime:
    return datetime.utcnow()


def _stale_before(now: datetime | None = None) -> datetime:
    current = now or _now_utc()
    return current - timedelta(seconds=settings.processing_lock_timeout_seconds)


def _clear_processing_lock_fields(material: Material) -> None:
    material.processing_owner = None
    material.processing_started_at = None
    material.processing_heartbeat_at = None


def _is_material_lock_stale(material: Material, stale_before: datetime) -> bool:
    heartbeat_at = material.processing_heartbeat_at
    started_at = material.processing_started_at
    if heartbeat_at is not None:
        return heartbeat_at < stale_before
    if started_at is not None:
        return started_at < stale_before
    return True


def _repair_stale_processing_materials(session: Session) -> None:
    processing_materials = session.exec(
        select(Material).where(Material.status == "processing")
    ).all()
    if not processing_materials:
        return

    stale_before = _stale_before()
    needs_commit = False
    for material in processing_materials:
        if material.id is None:
            continue
        task = processing_tasks.get(material.id)
        if task and not task.done():
            continue
        if not _is_material_lock_stale(material, stale_before):
            continue
        material.status = "failed"
        _clear_processing_lock_fields(material)
        session.add(material)
        needs_commit = True

    if needs_commit:
        session.commit()


def _claim_material_for_processing(material_id: int, owner: str) -> bool:
    now = _now_utc()
    stale_before = _stale_before(now)
    stale_lock_clause = or_(
        Material.processing_heartbeat_at < stale_before,
        and_(
            Material.processing_heartbeat_at.is_(None),
            Material.processing_started_at < stale_before,
        ),
        and_(
            Material.processing_heartbeat_at.is_(None),
            Material.processing_started_at.is_(None),
        ),
    )
    statement = (
        update(Material)
        .where(Material.id == material_id)
        .where(
            or_(
                Material.status != "processing",
                Material.processing_owner == owner,
                stale_lock_clause,
            )
        )
        .values(
            status="processing",
            processing_owner=owner,
            processing_started_at=now,
            processing_heartbeat_at=now,
        )
    )
    with Session(engine) as claim_session:
        result = claim_session.exec(statement)
        updated_rows = result.rowcount or 0
        if updated_rows < 1:
            claim_session.rollback()
            return False
        claim_session.commit()
        return True


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
        updated_rows = result.rowcount or 0
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
    original_path = await save_upload(file, settings.materials_dir)
    file_type = detect_file_type(original_path)

    if file_type == "unknown":
        raise HTTPException(status_code=400, detail="Unsupported file type.")

    material = Material(
        title=title,
        file_type=file_type,
        original_path=str(original_path),
        status="uploaded",
    )
    session.add(material)
    session.commit()
    session.refresh(material)
    return material


# For testing purposes, you can also add a simple endpoint to list all materials and get details of a specific material.
@router.get("", response_model=list[MaterialRead])
def list_materials(session: Session = Depends(get_session)):
    _repair_stale_processing_materials(session)
    statement = select(Material).order_by(desc(getattr(Material, "created_at")))
    return list(session.exec(statement).all())


# Get material details along with the count of sentences (if processed)
@router.get("/{material_id}", response_model=MaterialDetail)
def get_material(material_id: int, session: Session = Depends(get_session)):
    _repair_stale_processing_materials(session)
    material = session.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")

    return _build_material_detail(session, material)


def _build_material_detail(session: Session, material: Material) -> MaterialDetail:
    sentence_count = session.exec(
        select(func.count()).select_from(Sentence).where(Sentence.material_id == material.id)
    ).one()
    return MaterialDetail(**material.model_dump(), sentence_count=sentence_count)


def _mark_material_failed(material_id: int, owner: str | None = None) -> None:
    with Session(engine) as failure_session:
        material = failure_session.get(Material, material_id)
        if not material:
            return

        if owner is not None:
            lock_owned = material.status == "processing" and material.processing_owner == owner
            if not lock_owned:
                return

        material.status = "failed"
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

        audio_path = await asyncio.to_thread(extract_audio, source_path)
        duration = await asyncio.to_thread(get_audio_duration, audio_path)
        segments = await asyncio.to_thread(transcribe_audio, str(audio_path))
        sentence_candidates = await asyncio.to_thread(segment_to_sentences, segments)
        enriched_candidates, translations = await asyncio.gather(
            asyncio.to_thread(
                build_sentence_audio_metadata,
                audio_path,
                material_id,
                sentence_candidates,
            ),
            translate_sentences(item["source_text"] for item in sentence_candidates),
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

            for item, translation in zip(enriched_candidates, translations):
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
            _clear_processing_lock_fields(material)
            session.add(material)
            session.commit()
    except Exception:
        logger.exception("Failed processing material %s", material_id)
        await asyncio.to_thread(_mark_material_failed, material_id, owner)
    finally:
        heartbeat_stop_event.set()
        try:
            await heartbeat_task
        except Exception:
            logger.exception("Heartbeat task failed for material %s", material_id)


def _ensure_processing_task(material_id: int, owner: str) -> None:
    current_task = processing_tasks.get(material_id)
    if current_task and not current_task.done():
        return

    task = asyncio.create_task(_process_material_in_background(material_id, owner))
    processing_tasks[material_id] = task

    def _cleanup_task(done_task: asyncio.Task[None]) -> None:
        processing_tasks.pop(material_id, None)
        try:
            done_task.result()
        except BaseException:
            logger.exception("Background task crashed for material %s", material_id)

    task.add_done_callback(_cleanup_task)


# This endpoint triggers the processing of the material: extracting audio, transcribing, segmenting, translating, and saving sentences.
@router.post("/{material_id}/process", response_model=MaterialDetail)
async def process_material(material_id: int, session: Session = Depends(get_session)):
    _repair_stale_processing_materials(session)

    material = session.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")

    claimed = await asyncio.to_thread(
        _claim_material_for_processing,
        material_id,
        WORKER_INSTANCE_ID,
    )

    session.expire_all()
    latest_material = session.get(Material, material_id)
    if not latest_material:
        raise HTTPException(status_code=404, detail="Material not found.")

    if claimed:
        _ensure_processing_task(material_id, WORKER_INSTANCE_ID)

    return _build_material_detail(session, latest_material)


@router.get("/{material_id}/audio")
def get_material_audio(material_id: int, session: Session = Depends(get_session)):
    material = session.get(Material, material_id)
    if not material or not material.audio_path:
        raise HTTPException(status_code=404, detail="Audio not found.")
    return FileResponse(material.audio_path, media_type="audio/wav")


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
