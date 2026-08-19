from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import update
from sqlmodel import Session, select

from app.core.config import settings
from app.core.database import engine
from app.models.material import Material
from app.models.sentence import Sentence
from app.services.asr_router import MATERIAL_TRANSCRIPTION, transcribe_for_scene
from app.services.job_service import update_job
from app.services.media_service import (
    build_sentence_audio_metadata,
    extract_audio,
    get_audio_duration,
    transcode_video_for_storage,
)
from app.services.segmentation_service import segment_to_sentences
from app.services.translation_service import translate_sentences

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _clear_processing_lock(material: Material) -> None:
    material.processing_owner = None
    material.processing_started_at = None
    material.processing_heartbeat_at = None


def _rowcount(result: object) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


def _touch_processing_lock(material_id: int, owner: str) -> bool:
    statement = (
        update(Material)
        .where(Material.id == material_id)
        .where(Material.status == "processing")
        .where(Material.processing_owner == owner)
        .values(processing_heartbeat_at=_now_utc())
    )
    with Session(engine) as session:
        result = session.exec(statement)
        if _rowcount(result) < 1:
            session.rollback()
            return False
        session.commit()
        return True


def _owns_processing_lock(material_id: int, owner: str) -> bool:
    with Session(engine) as session:
        material = session.get(Material, material_id)
        return bool(
            material
            and material.status == "processing"
            and material.processing_owner == owner
        )


async def _run_lock_heartbeat(
    material_id: int,
    owner: str,
    stop_event: asyncio.Event,
) -> None:
    interval = max(settings.processing_lock_heartbeat_seconds, 1)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            pass

        if await asyncio.to_thread(_touch_processing_lock, material_id, owner):
            continue

        logger.warning(
            "Lost processing lock heartbeat for material %s owned by %s.",
            material_id,
            owner,
        )
        stop_event.set()
        return


def normalize_translations(
    sentence_candidates: list[dict[str, object]],
    translations: list[str],
) -> list[str]:
    """Match translations to sentences without leaking diagnostics into content."""
    expected_count = len(sentence_candidates)
    normalized = list(translations[:expected_count])
    normalized.extend("" for _ in range(expected_count - len(normalized)))
    return normalized


def _mark_material_failed(
    material_id: int,
    owner: str,
    error_message: str,
) -> None:
    with Session(engine) as session:
        material = session.get(Material, material_id)
        if not material:
            return
        if material.status != "processing" or material.processing_owner != owner:
            return

        material.status = "failed"
        material.processing_stage = "failed"
        material.error_message = error_message
        _clear_processing_lock(material)
        session.add(material)
        session.commit()


async def _run_processing_pipeline(material_id: int, owner: str) -> None:
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
            content_language = material.content_language
            translation_language = material.translation_language
            audio_source_path = source_path
            if is_video:
                audio_source_path = await asyncio.to_thread(
                    transcode_video_for_storage,
                    source_path,
                )
                source_path.unlink(missing_ok=True)
                material.original_path = str(audio_source_path)
                material.processing_stage = "extracting_audio"
                material.processing_progress = 20
                session.add(material)
                session.commit()

        audio_path = await asyncio.to_thread(extract_audio, audio_source_path)
        duration_probe_path = audio_source_path if is_video else audio_path
        duration = await asyncio.to_thread(get_audio_duration, duration_probe_path)
        segments = await asyncio.to_thread(
            transcribe_for_scene,
            MATERIAL_TRANSCRIPTION,
            str(audio_path),
            word_timestamps=True,
            language=content_language,
        )
        sentence_candidates = await asyncio.to_thread(
            segment_to_sentences,
            segments,
            language=content_language,
        )
        enriched_candidates, translations = await asyncio.gather(
            asyncio.to_thread(
                build_sentence_audio_metadata,
                audio_path,
                material_id,
                sentence_candidates,
                duration,
            ),
            translate_sentences(
                (item["source_text"] for item in sentence_candidates),
                source_language=content_language,
                target_language=translation_language,
            ),
        )
        if len(enriched_candidates) != len(sentence_candidates):
            raise RuntimeError(
                "Sentence metadata count mismatch: "
                f"expected={len(sentence_candidates)} got={len(enriched_candidates)}"
            )
        if len(translations) != len(enriched_candidates):
            logger.warning(
                "Translation count mismatch for material %s: expected=%s got=%s.",
                material_id,
                len(enriched_candidates),
                len(translations),
            )
        normalized_translations = normalize_translations(
            enriched_candidates,
            translations,
        )

        if not await asyncio.to_thread(_owns_processing_lock, material_id, owner):
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

            for item, translation in zip(
                enriched_candidates,
                normalized_translations,
                strict=True,
            ):
                session.add(
                    Sentence(
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
                )

            material.audio_path = str(audio_path)
            material.duration = duration
            material.status = "ready"
            material.processing_stage = "completed"
            material.processing_progress = 100
            material.error_message = None
            _clear_processing_lock(material)
            session.add(material)
            session.commit()
    except Exception as exc:
        logger.exception("Failed processing material %s", material_id)
        await asyncio.to_thread(
            _mark_material_failed,
            material_id,
            owner,
            str(exc)[:2000],
        )
    finally:
        heartbeat_stop_event.set()
        try:
            await heartbeat_task
        except Exception:
            logger.exception("Heartbeat task failed for material %s", material_id)


async def process_material_job(material_id: int, job_id: str) -> None:
    """Process one queued material while the worker owns its lock."""
    with Session(engine) as session:
        material = session.get(Material, material_id)
        if not material:
            raise RuntimeError("Material no longer exists.")
        now = _now_utc()
        material.status = "processing"
        material.processing_owner = job_id
        material.processing_started_at = now
        material.processing_heartbeat_at = now
        material.processing_stage = "transcribing"
        material.processing_progress = 15
        material.error_message = None
        session.add(material)
        session.commit()

    update_job(job_id, stage="transcribing_material", progress=25)
    await _run_processing_pipeline(material_id, job_id)

    with Session(engine) as session:
        material = session.get(Material, material_id)
        if not material or material.status != "ready":
            message = material.error_message if material else "Material processing failed."
            raise RuntimeError(message)
    update_job(job_id, stage="material_ready", progress=95)
