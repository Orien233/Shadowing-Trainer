from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, select

from app.core.config import settings
from app.core.database import engine
from app.models.material import Material
from app.models.sentence import Sentence
from app.models.text_practice import TextPractice
from app.schemas.text_practice import TTSOptions
from app.services.ai.tts.base import TTSRequest
from app.services.job_service import update_job
from app.services.media_service import get_audio_duration
from app.services.provider_factory import get_provider, get_provider_record

_SPEEDS = {"slow": 0.8, "normal": 1.0, "fast": 1.2}


def split_practice_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def queue_tts(session: Session, practice: TextPractice, options: TTSOptions):
    from app.services.job_service import enqueue_job

    provider_record = get_provider_record(session, "tts", options.provider_id)
    practice.tts_provider_id = provider_record.id
    practice.tts_options_json = options.model_dump_json()
    practice.tts_status = "queued"
    job = enqueue_job(session, "tts_synthesis", {"text_practice_id": practice.id})
    practice.tts_job_id = job.id
    practice.updated_at = datetime.now(UTC)
    session.add(practice)
    session.commit()
    return job


def _merge_audio(segment_paths: list[Path], target_path: Path) -> None:
    concat_file = target_path.with_suffix(".concat.txt")
    concat_file.write_text("".join(f"file '{path.as_posix()}'\n" for path in segment_paths), encoding="utf-8")
    try:
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:a", "libmp3lame", "-q:a", "3", str(target_path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    finally:
        concat_file.unlink(missing_ok=True)


def run_tts_synthesis(job_id: str, payload: dict) -> dict:
    practice_id = int(payload["text_practice_id"])
    with Session(engine) as session:
        practice = session.get(TextPractice, practice_id)
        if not practice:
            raise RuntimeError("Text practice no longer exists.")
        options = TTSOptions.model_validate_json(practice.tts_options_json)
        provider = get_provider(session, "tts", practice.tts_provider_id)
        sentences = split_practice_sentences(practice.body)
        if not sentences:
            raise ValueError("Text practice has no sentences to synthesize.")
        title = practice.title
    output_dir = settings.sentence_audio_dir / f"text_practice_{practice_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, sentence in enumerate(sentences, start=1):
        update_job(job_id, stage=f"synthesizing_sentence_{index}", progress=max(5, int(index / len(sentences) * 75)))
        audio = provider.synthesize(TTSRequest(text=sentence, voice=options.voice, model=options.model, speed=_SPEEDS[options.speed_preset], accent=options.accent, gender=options.gender))
        path = output_dir / f"{index:04d}.mp3"
        path.write_bytes(audio)
        paths.append(path)
    update_job(job_id, stage="merging_audio", progress=82)
    merged_path = settings.audio_dir / f"text_practice_{practice_id}.mp3"
    _merge_audio(paths, merged_path)
    durations = [get_audio_duration(path) for path in paths]
    total_duration = get_audio_duration(merged_path)
    update_job(job_id, stage="creating_material", progress=92)
    with Session(engine) as session:
        practice = session.get(TextPractice, practice_id)
        if not practice:
            raise RuntimeError("Text practice was deleted during synthesis.")
        if practice.material_id:
            old_sentences = session.exec(select(Sentence).where(Sentence.material_id == practice.material_id)).all()
            for old in old_sentences:
                session.delete(old)
            material = session.get(Material, practice.material_id)
        else:
            material = None
        if not material:
            material = Material(title=title, file_type="audio", original_path=str(merged_path), source_type="text_tts", text_practice_id=practice_id)
            session.add(material)
            session.flush()
        material.audio_path, material.duration, material.status = str(merged_path), total_duration, "ready"
        material.processing_stage, material.processing_progress, material.error_message = "completed", 100, None
        offset = 0.0
        for index, (sentence_text, duration, clip_path) in enumerate(zip(sentences, durations, paths), start=1):
            end = offset + duration
            session.add(Sentence(material_id=material.id, display_order=index, start_time=offset, end_time=end, original_start_time=offset, original_end_time=end, clip_audio_path=str(clip_path), clip_duration=duration, source_text=sentence_text))
            offset = end
        practice.tts_audio_path, practice.tts_status, practice.material_id = str(merged_path), "ready", material.id
        practice.updated_at = datetime.now(UTC)
        session.add(material); session.add(practice); session.commit(); session.refresh(material)
        return {"text_practice_id": practice_id, "material_id": material.id}
