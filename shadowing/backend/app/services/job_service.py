from __future__ import annotations

import asyncio
import json
import logging
import shutil
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import update
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.models.evaluation import Evaluation
from app.models.job import Job
from app.models.recording import Recording
from app.models.sentence import Sentence
from app.models.material import Material
from app.services.evaluation_service import evaluate_recording
from app.services.material_score_service import record_material_sentence_score
from app.services.media_service import extract_audio

logger = logging.getLogger(__name__)
WORKER_ID = f"{socket.gethostname()}:{id(engine)}"
_worker_task: asyncio.Task[None] | None = None
_stop_event: asyncio.Event | None = None


def utcnow() -> datetime:
    return datetime.now(UTC)


def enqueue_job(session: Session, kind: str, payload: dict[str, Any]) -> Job:
    job = Job(kind=kind, payload=json.dumps(payload, ensure_ascii=False))
    session.add(job)
    session.flush()
    return job


def _claim_next_job() -> str | None:
    with Session(engine) as session:
        job = session.query(Job).filter(Job.status == "queued").order_by(Job.created_at).first()
        if not job:
            return None
        result = session.exec(
            update(Job)
            .where(Job.id == job.id)
            .where(Job.status == "queued")
            .values(
                status="running", stage="starting", progress=1, worker_id=WORKER_ID,
                attempts=Job.attempts + 1, started_at=utcnow(), error_message=None,
            )
        )
        if not getattr(result, "rowcount", 0):
            session.rollback()
            return None
        session.commit()
        return job.id


def update_job(job_id: str, *, stage: str, progress: int) -> None:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job and job.status == "running":
            job.stage = stage
            job.progress = max(0, min(progress, 100))
            session.add(job)
            session.commit()


def finish_job(job_id: str, *, result: dict[str, Any] | None = None) -> None:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return
        job.status = "succeeded"
        job.stage = "completed"
        job.progress = 100
        job.result = json.dumps(result, ensure_ascii=False) if result is not None else None
        job.finished_at = utcnow()
        session.add(job)
        session.commit()


def fail_job(job_id: str, message: str) -> None:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return
        job.status = "failed"
        job.stage = "failed"
        job.error_message = message[:2000]
        job.finished_at = utcnow()
        session.add(job)
        session.commit()


async def _run_evaluation(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    recording_id = int(payload["recording_id"])
    with Session(engine) as session:
        recording = session.get(Recording, recording_id)
        if not recording:
            raise RuntimeError("Recording no longer exists.")
        sentence = session.get(Sentence, recording.sentence_id)
        if not sentence:
            raise RuntimeError("Sentence no longer exists.")
        source_path = Path(recording.audio_path)
        reference_text = sentence.source_text
        reference_duration = max(sentence.clip_duration or sentence.end_time - sentence.start_time, 0.1)
        reference_audio_path = sentence.clip_audio_path
        material = session.get(Material, sentence.material_id)
        content_language = material.content_language if material else None

    update_job(job_id, stage="normalizing_audio", progress=15)
    normalized_path = await asyncio.to_thread(extract_audio, source_path)
    if normalized_path != source_path:
        source_path.unlink(missing_ok=True)
    update_job(job_id, stage="scoring", progress=35)
    result = await asyncio.to_thread(
        evaluate_recording,
        reference_text=reference_text,
        reference_duration=reference_duration,
        recording_path=str(normalized_path),
        reference_audio_path=reference_audio_path,
        content_language=content_language,
    )

    update_job(job_id, stage="saving_result", progress=90)
    with Session(engine) as session:
        recording = session.get(Recording, recording_id)
        sentence = session.get(Sentence, recording.sentence_id) if recording else None
        if not recording or not sentence:
            raise RuntimeError("Recording was deleted while scoring.")
        recording.audio_path = str(normalized_path)
        recording.duration = result["duration"]
        recording.asr_text = result["asr_text"]
        recording.status = "completed"
        recording.error_message = None
        evaluation = Evaluation(
            recording_id=recording.id,
            completeness_score=result["completeness_score"], fluency_score=result["fluency_score"],
            sync_score=result["sync_score"], pronunciation_score=result["pronunciation_score"],
            overall_score=result["overall_score"], feedback=result["feedback"],
            suggestion=result["suggestion"], raw_metrics=result["raw_metrics"],
        )
        session.add(recording)
        session.add(evaluation)
        session.flush()
        record_material_sentence_score(
            session=session, material_id=sentence.material_id, sentence_id=sentence.id,
            evaluation=evaluation, recording_id=recording.id, user_id=payload.get("user_id"),
        )
        session.commit()
        session.refresh(evaluation)
        return {"recording_id": recording.id, "evaluation": evaluation.model_dump(mode="json")}


async def _run_material_processing(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    update_job(job_id, stage="processing_material", progress=10)
    from app.services.material_processing_service import process_material_job

    material_id = int(payload["material_id"])
    await process_material_job(material_id, job_id)
    return {"material_id": material_id}


async def _run_storage_cleanup(_job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    for raw_path in payload.get("paths", []):
        path = Path(raw_path)
        try:
            path.resolve().relative_to(settings.data_path.resolve())
        except ValueError:
            raise RuntimeError(f"Refusing cleanup outside data directory: {path}")
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    return {"deleted": len(payload.get("paths", []))}


async def _run_tts_synthesis(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from app.services.tts_service import run_tts_synthesis
    return await asyncio.to_thread(run_tts_synthesis, job_id, payload)


JOB_HANDLERS = {
    "evaluation": _run_evaluation,
    "material_processing": _run_material_processing,
    "storage_cleanup": _run_storage_cleanup,
    "tts_synthesis": _run_tts_synthesis,
}


async def _run_job(job_id: str) -> None:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return
        kind, payload = job.kind, json.loads(job.payload)
    try:
        handler = JOB_HANDLERS.get(kind)
        if not handler:
            raise RuntimeError(f"Unsupported job kind: {kind}")
        result = await handler(job_id, payload)
        finish_job(job_id, result=result)
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        if kind == "evaluation":
            with Session(engine) as session:
                recording = session.get(Recording, payload.get("recording_id"))
                if recording:
                    recording.status = "failed"
                    recording.error_message = str(exc)[:2000]
                    session.add(recording)
                    session.commit()
        if kind == "material_processing":
            with Session(engine) as session:
                from app.models.material import Material
                material = session.get(Material, payload.get("material_id"))
                if material:
                    material.status = "failed"
                    material.error_message = str(exc)[:2000]
                    material.processing_stage = "failed"
                    session.add(material)
                    session.commit()
        if kind == "tts_synthesis":
            with Session(engine) as session:
                from app.models.text_practice import TextPractice
                practice = session.get(TextPractice, payload.get("text_practice_id"))
                # Do not let an obsolete job overwrite a newer queue request
                # or an edited practice that deliberately cleared ownership.
                if practice and practice.tts_job_id == job_id:
                    practice.tts_status = "failed"
                    session.add(practice)
                    session.commit()
        fail_job(job_id, str(exc))


async def _worker_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        job_id = await asyncio.to_thread(_claim_next_job)
        if job_id:
            await _run_job(job_id)
            continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.job_poll_interval_seconds)
        except asyncio.TimeoutError:
            pass


def recover_interrupted_jobs() -> None:
    with Session(engine) as session:
        jobs = session.query(Job).filter(Job.status == "running").all()
        for job in jobs:
            job.status = "queued"
            job.stage = "recovered_after_restart"
            job.worker_id = None
            session.add(job)
        session.commit()


def start_job_worker() -> None:
    global _worker_task, _stop_event
    if _worker_task and not _worker_task.done():
        return
    recover_interrupted_jobs()
    _stop_event = asyncio.Event()
    _worker_task = asyncio.create_task(_worker_loop(_stop_event), name="durable-job-worker")


async def stop_job_worker() -> None:
    if _stop_event:
        _stop_event.set()
    if _worker_task:
        await _worker_task


def retry_job(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if not job:
        raise KeyError(job_id)
    if job.status not in {"failed", "cancelled"}:
        raise ValueError("Only failed or cancelled jobs can be retried.")
    if job.kind == "tts_synthesis":
        from app.models.text_practice import TextPractice
        from app.services.tts_service import (
            TTSJobObsoleteError,
            require_retryable_tts_snapshot,
        )

        try:
            payload = json.loads(job.payload)
            practice_id = int(payload["text_practice_id"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                "This TTS job has an invalid payload and cannot be retried."
            ) from exc
        practice = session.get(TextPractice, practice_id)
        if not practice:
            raise ValueError(
                "This TTS job cannot be retried because its text practice no longer exists."
            )
        expected_owner_id = practice.tts_job_id
        if expected_owner_id and expected_owner_id != job.id:
            current_owner = session.get(Job, expected_owner_id)
            if current_owner and current_owner.status in {"queued", "running"}:
                raise ValueError(
                    "A newer TTS job is already queued or running for this text practice."
                )
        try:
            require_retryable_tts_snapshot(practice, payload)
        except TTSJobObsoleteError as exc:
            raise ValueError(str(exc)) from exc
        # Reclaim ownership in the same transaction that requeues the durable
        # job, so the worker cannot observe a queued TTS job with stale owner
        # metadata on its practice.
        ownership_filter = (
            TextPractice.tts_job_id.is_(None)
            if expected_owner_id is None
            else TextPractice.tts_job_id == expected_owner_id
        )
        ownership_result = session.exec(
            update(TextPractice)
            .where(TextPractice.id == practice.id)
            .where(ownership_filter)
            .values(
                tts_job_id=job.id,
                tts_status="queued",
                updated_at=utcnow(),
            )
        )
        if not getattr(ownership_result, "rowcount", 0):
            session.rollback()
            raise ValueError(
                "A newer TTS job claimed this text practice while the retry was being validated."
            )
    job.status = "queued"
    job.stage = "queued"
    job.progress = 0
    job.error_message = None
    job.finished_at = None
    session.add(job)
    session.commit()
    session.refresh(job)
    return job
