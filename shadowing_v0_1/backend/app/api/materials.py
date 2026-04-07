import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc
from sqlmodel import Session, func, select

from app.core.config import settings
from app.core.database import engine, get_session
from app.models.material import Material
from app.models.sentence import Sentence
from app.schemas.material import MaterialDetail, MaterialRead
from app.services.media_service import (
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


def _repair_stale_processing_materials(session: Session) -> None:
    processing_materials = session.exec(
        select(Material).where(Material.status == "processing")
    ).all()
    needs_commit = False
    for material in processing_materials:
        if material.id is None:
            continue
        task = processing_tasks.get(material.id)
        if task and not task.done():
            continue
        material.status = "failed"
        session.add(material)
        needs_commit = True
    if needs_commit:
        session.commit()

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


def _mark_material_failed(material_id: int) -> None:
    with Session(engine) as session:
        material = session.get(Material, material_id)
        if not material:
            return
        material.status = "failed"
        session.add(material)
        session.commit()


async def _process_material_in_background(material_id: int) -> None:
    try:
        with Session(engine) as session:
            material = session.get(Material, material_id)
            if not material:
                return
            source_path = Path(material.original_path)
            material.status = "processing"
            session.add(material)
            session.commit()

        audio_path = await asyncio.to_thread(extract_audio, source_path)
        duration = await asyncio.to_thread(get_audio_duration, audio_path)
        segments = await asyncio.to_thread(transcribe_audio, str(audio_path))
        sentence_candidates = await asyncio.to_thread(segment_to_sentences, segments)
        translations = await translate_sentences(
            item["source_text"] for item in sentence_candidates
        )

        with Session(engine) as session:
            material = session.get(Material, material_id)
            if not material:
                return

            existing_sentences = session.exec(
                select(Sentence).where(Sentence.material_id == material_id)
            ).all()
            for existing in existing_sentences:
                session.delete(existing)
            session.commit()

            for item, translation in zip(sentence_candidates, translations):
                sentence = Sentence(
                    material_id=material_id,
                    display_order=item["display_order"],
                    start_time=item["start_time"],
                    end_time=item["end_time"],
                    source_text=item["source_text"],
                    translation=translation,
                )
                session.add(sentence)

            material.audio_path = str(audio_path)
            material.duration = duration
            material.status = "ready"
            session.add(material)
            session.commit()
    except Exception:
        logger.exception("Failed processing material %s", material_id)
        _mark_material_failed(material_id)


def _ensure_processing_task(material_id: int) -> None:
    current_task = processing_tasks.get(material_id)
    if current_task and not current_task.done():
        return

    task = asyncio.create_task(_process_material_in_background(material_id))
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
    material = session.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")

    if material.status != "processing":
        material.status = "processing"
        session.add(material)
        session.commit()
        session.refresh(material)

    _ensure_processing_task(material_id)
    return _build_material_detail(session, material)


@router.get("/{material_id}/audio")
def get_material_audio(material_id: int, session: Session = Depends(get_session)):
    material = session.get(Material, material_id)
    if not material or not material.audio_path:
        raise HTTPException(status_code=404, detail="Audio not found.")
    return FileResponse(material.audio_path, media_type="audio/wav")
