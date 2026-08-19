from __future__ import annotations

import asyncio
import re
import shutil
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
from app.services.ai.audio_types import ProviderCapability, TTSResult
from app.services.job_service import update_job
from app.services.media_service import get_audio_duration
from app.services.provider_factory import get_provider, require_provider_capabilities
from app.services.language_catalog import normalize_language_tag
from app.services.translation_service import translate_sentences

_SPEEDS = {"slow": 0.8, "normal": 1.0, "fast": 1.2}
_SENTENCE_TERMINATORS = frozenset(".!?…。！？？｡؟۔।॥")
_TRAILING_SENTENCE_CLOSERS = frozenset("\"'”’»）)]}】〉》」』")


class TTSJobObsoleteError(RuntimeError):
    """Raised when an immutable TTS job no longer owns its text practice."""


def _build_tts_snapshot(
    practice: TextPractice,
    *,
    provider_id: int,
    options: TTSOptions,
) -> dict[str, object]:
    """Serialize every practice value that determines a TTS material."""
    return {
        "title": practice.title,
        "body": practice.body,
        "target_language": normalize_language_tag(practice.target_language),
        "translation_language": normalize_language_tag(practice.translation_language),
        "provider_id": provider_id,
        "options": options.model_dump(mode="json"),
    }


def _snapshot_from_payload(practice: TextPractice, payload: dict) -> dict[str, object]:
    """Read a snapshot, recovering old id-only payloads only while owned.

    Jobs created before snapshotting can resume from their practice's current
    values, but only if that practice still names the job as its active TTS
    job. New jobs always carry a complete immutable snapshot.
    """
    raw_snapshot = payload.get("snapshot")
    if raw_snapshot is None:
        options = TTSOptions.model_validate_json(practice.tts_options_json)
        if practice.tts_provider_id is None:
            raise RuntimeError("Legacy TTS job has no selected provider.")
        return _build_tts_snapshot(
            practice,
            provider_id=practice.tts_provider_id,
            options=options,
        )
    if not isinstance(raw_snapshot, dict):
        raise RuntimeError("TTS job snapshot is invalid.")
    required = {"title", "body", "target_language", "translation_language", "provider_id", "options"}
    if not required.issubset(raw_snapshot):
        raise RuntimeError("TTS job snapshot is incomplete.")
    try:
        return {
            "title": str(raw_snapshot["title"]),
            "body": str(raw_snapshot["body"]),
            "target_language": normalize_language_tag(str(raw_snapshot["target_language"])),
            "translation_language": normalize_language_tag(str(raw_snapshot["translation_language"])),
            "provider_id": int(raw_snapshot["provider_id"]),
            "options": TTSOptions.model_validate(raw_snapshot["options"]).model_dump(mode="json"),
        }
    except (TypeError, ValueError) as exc:
        raise RuntimeError("TTS job snapshot is invalid.") from exc


def _require_current_snapshot(
    practice: TextPractice,
    *,
    job_id: str,
    snapshot: dict[str, object],
) -> None:
    matches = practice.tts_job_id == job_id and _practice_matches_snapshot(
        practice,
        snapshot,
    )
    if not matches:
        raise TTSJobObsoleteError(
            "TTS job was superseded because the text practice was edited or re-queued."
        )


def _practice_matches_snapshot(
    practice: TextPractice,
    snapshot: dict[str, object],
) -> bool:
    """Compare every persisted input that determines a TTS material."""
    try:
        current_options = TTSOptions.model_validate_json(
            practice.tts_options_json
        ).model_dump(mode="json")
        snapshot_options = TTSOptions.model_validate(
            snapshot["options"]
        ).model_dump(mode="json")
        snapshot_provider_id = int(snapshot["provider_id"])
        target_language = normalize_language_tag(practice.target_language)
        translation_language = normalize_language_tag(practice.translation_language)
    except (KeyError, TypeError, ValueError):
        return False
    return (
        practice.title == snapshot["title"]
        and practice.body == snapshot["body"]
        and target_language == snapshot["target_language"]
        and translation_language == snapshot["translation_language"]
        and practice.tts_provider_id == snapshot_provider_id
        and current_options == snapshot_options
    )


def require_retryable_tts_snapshot(
    practice: TextPractice,
    payload: dict,
) -> dict[str, object]:
    """Validate that a failed TTS job can safely reclaim its practice.

    Legacy jobs without an immutable snapshot cannot prove that the practice
    was not edited after enqueueing. They must be queued again from the text
    practice instead of being retried through the generic Job endpoint.
    """
    if payload.get("snapshot") is None:
        raise TTSJobObsoleteError(
            "This legacy TTS job has no immutable snapshot and cannot be retried safely. "
            "Create a new TTS job from the text practice."
        )
    snapshot = _snapshot_from_payload(practice, payload)
    if not _practice_matches_snapshot(practice, snapshot):
        raise TTSJobObsoleteError(
            "This TTS job cannot be retried because the text, languages, provider, "
            "or synthesis options were edited after it was queued. Create a new TTS job."
        )
    return snapshot


def _job_output_token(job_id: str) -> str:
    """Return a path-safe token so stale jobs cannot overwrite valid audio."""
    token = re.sub(r"[^a-zA-Z0-9_-]", "_", str(job_id))
    if not token:
        raise ValueError("TTS job id cannot be empty.")
    return token


def _require_current_job_in_database(
    practice_id: int,
    *,
    job_id: str,
    snapshot: dict[str, object],
) -> None:
    with Session(engine) as session:
        practice = session.get(TextPractice, practice_id)
        if not practice:
            raise RuntimeError("Text practice was deleted while TTS was running.")
        _require_current_snapshot(practice, job_id=job_id, snapshot=snapshot)


def split_practice_sentences(text: str) -> list[str]:
    """Split a practice passage without requiring spaces after punctuation.

    CJK scripts commonly place sentences directly next to one another, while
    Arabic and Devanagari have their own sentence marks.  A small scanner is
    more reliable than a whitespace-based regex here: it keeps every
    non-whitespace character, retains punctuation on its sentence, and also
    handles closing quotes/brackets and repeated marks such as ``?!``.
    """
    value = str(text or "").strip()
    if not value:
        return []

    sentences: list[str] = []
    current: list[str] = []

    def flush() -> None:
        sentence = "".join(current).strip()
        current.clear()
        if sentence:
            sentences.append(sentence)

    index = 0
    while index < len(value):
        character = value[index]
        if character in "\r\n":
            flush()
            index += 1
            while index < len(value) and value[index].isspace():
                index += 1
            continue

        current.append(character)
        index += 1
        if character not in _SENTENCE_TERMINATORS:
            continue

        # A full stop inside an alphanumeric token is not a sentence boundary.
        # This covers decimal numbers, host names, email-like text, and compact
        # initialisms without weakening no-whitespace CJK sentence splitting.
        if (
            character == "."
            and index >= 2
            and index < len(value)
            and value[index - 2].isalnum()
            and value[index].isalnum()
        ):
            continue

        # A terminal cluster belongs to the preceding sentence.  This avoids
        # emitting fragments for 「Really?!」 or sentences followed by quotes.
        while index < len(value) and value[index] in (_SENTENCE_TERMINATORS | _TRAILING_SENTENCE_CLOSERS):
            current.append(value[index])
            index += 1
        flush()
        while index < len(value) and value[index].isspace():
            index += 1

    flush()
    return sentences


def queue_tts(session: Session, practice: TextPractice, options: TTSOptions):
    from app.services.job_service import enqueue_job

    provider_record = require_provider_capabilities(
        session,
        "tts",
        {ProviderCapability.SYNTHESIZE},
        options.provider_id,
    )
    # Snapshot the language at enqueue time. The worker may run after a user
    # edits a practice, but audio must retain the reviewed target language.
    target_language = normalize_language_tag(practice.target_language)
    if options.language and options.language != target_language:
        raise ValueError(
            "TTS language must match the text practice target language. "
            "Edit the practice language before creating TTS."
        )
    language = target_language
    frozen_options = options.model_copy(update={"language": language})
    practice.tts_provider_id = provider_record.id
    practice.tts_options_json = frozen_options.model_dump_json()
    practice.tts_status = "queued"
    snapshot = _build_tts_snapshot(
        practice,
        provider_id=provider_record.id,
        options=frozen_options,
    )
    job = enqueue_job(
        session,
        "tts_synthesis",
        {"text_practice_id": practice.id, "snapshot": snapshot},
    )
    practice.tts_job_id = job.id
    practice.updated_at = datetime.now(UTC)
    session.add(practice)
    session.commit()
    return job


def _ffmpeg(command: list[str], *, operation: str) -> None:
    """Run ffmpeg with an actionable failure instead of opaque job stderr."""
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg is required for TTS audio normalization but was not found on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"FFmpeg failed while {operation}: {detail[-1000:]}") from exc


def _safe_extension(value: str) -> str:
    extension = value.strip().lower().lstrip(".")
    if not re.fullmatch(r"[a-z0-9]{1,10}", extension):
        raise ValueError("TTS adapter returned an unsafe audio file extension.")
    return extension


def _normalize_sentence_audio(result: TTSResult, *, index: int, output_dir: Path) -> Path:
    """Convert every provider response into a uniform, playable WAV clip.

    The sentence trainer receives only 24 kHz mono WAV files.  This makes
    concat deterministic across providers and, crucially, supplies FFmpeg
    with explicit decoding details for headerless PCM responses.
    """
    extension = _safe_extension(result.extension)
    source_path = output_dir / f"{index:04d}.source.{extension}"
    target_path = output_dir / f"{index:04d}.wav"
    temporary_path = output_dir / f"{index:04d}.normalizing.wav"
    source_path.write_bytes(result.audio)
    command = ["ffmpeg", "-y"]
    if result.raw_pcm:
        command.extend(
            [
                "-f", result.raw_pcm.sample_format,
                "-ar", str(result.raw_pcm.sample_rate),
                "-ac", str(result.raw_pcm.channels),
            ]
        )
    command.extend(
        [
            "-i", str(source_path),
            "-vn",
            "-ar", "24000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(temporary_path),
        ]
    )
    try:
        _ffmpeg(command, operation=f"normalizing TTS sentence {index}")
        temporary_path.replace(target_path)
    finally:
        temporary_path.unlink(missing_ok=True)
        source_path.unlink(missing_ok=True)
    return target_path


def _merge_audio(segment_paths: list[Path], target_path: Path) -> None:
    concat_file = target_path.with_suffix(".concat.txt")
    # FFmpeg resolves paths in a concat list relative to the list itself.  The
    # application data directories are intentionally configured with relative
    # paths (for portable local installs), so writing those values verbatim
    # would turn e.g. ``data/audio/sentences/...`` into
    # ``data/audio/data/audio/sentences/...``.  Use absolute, concat-safe paths
    # to make the merge independent of the process working directory.
    def concat_path(path: Path) -> str:
        return path.resolve().as_posix().replace("'", r"'\\''")

    concat_file.write_text(
        "".join(f"file '{concat_path(path)}'\n" for path in segment_paths),
        encoding="utf-8",
    )
    try:
        _ffmpeg(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:a", "libmp3lame", "-q:a", "3", str(target_path)],
            operation="merging normalized TTS sentences",
        )
    finally:
        concat_file.unlink(missing_ok=True)


def _remove_obsolete_tts_outputs(output_dir: Path, merged_path: Path) -> None:
    """Delete partial artifacts that can never belong to the active practice."""
    shutil.rmtree(output_dir, ignore_errors=True)
    merged_path.unlink(missing_ok=True)


def run_tts_synthesis(job_id: str, payload: dict) -> dict:
    practice_id = int(payload["text_practice_id"])
    with Session(engine) as session:
        practice = session.get(TextPractice, practice_id)
        if not practice:
            raise RuntimeError("Text practice no longer exists.")
        snapshot = _snapshot_from_payload(practice, payload)
        _require_current_snapshot(practice, job_id=job_id, snapshot=snapshot)
        options = TTSOptions.model_validate(snapshot["options"])
        # Recheck the static Adapter contract when a persisted job resumes.
        # A provider can be disabled or replaced after the job was enqueued.
        provider_record = require_provider_capabilities(
            session,
            "tts",
            {ProviderCapability.SYNTHESIZE},
            int(snapshot["provider_id"]),
        )
        provider = get_provider(session, "tts", provider_record.id)
        sentences = split_practice_sentences(str(snapshot["body"]))
        if not sentences:
            raise ValueError("Text practice has no sentences to synthesize.")
        title = str(snapshot["title"])
    update_job(job_id, stage="translating_sentences", progress=3)
    translations = asyncio.run(
        translate_sentences(
            sentences,
            source_language=str(snapshot["target_language"]),
            target_language=str(snapshot["translation_language"]),
        )
    )
    if len(translations) < len(sentences):
        translations.extend("" for _ in range(len(sentences) - len(translations)))
    translations = translations[: len(sentences)]
    _require_current_job_in_database(practice_id, job_id=job_id, snapshot=snapshot)
    output_token = _job_output_token(job_id)
    output_dir = settings.sentence_audio_dir / f"text_practice_{practice_id}_{output_token}"
    merged_path = settings.audio_dir / f"text_practice_{practice_id}_{output_token}.mp3"
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    try:
        for index, sentence in enumerate(sentences, start=1):
            # Stop before another potentially billable provider request when
            # an edit or newer queue request superseded this snapshot.
            _require_current_job_in_database(practice_id, job_id=job_id, snapshot=snapshot)
            update_job(job_id, stage=f"synthesizing_sentence_{index}", progress=max(5, int(index / len(sentences) * 75)))
            result = provider.synthesize(TTSRequest(text=sentence, language=options.language, voice=options.voice, model=options.model, speed=_SPEEDS[options.speed_preset], accent=options.accent, gender=options.gender))
            path = _normalize_sentence_audio(result, index=index, output_dir=output_dir)
            paths.append(path)
        # Avoid merging when the final provider call was superseded while it
        # was in flight.
        _require_current_job_in_database(practice_id, job_id=job_id, snapshot=snapshot)
    except TTSJobObsoleteError:
        _remove_obsolete_tts_outputs(output_dir, merged_path)
        raise
    update_job(job_id, stage="merging_audio", progress=82)
    _merge_audio(paths, merged_path)
    durations = [get_audio_duration(path) for path in paths]
    total_duration = get_audio_duration(merged_path)
    update_job(job_id, stage="creating_material", progress=92)
    with Session(engine) as session:
        practice = session.get(TextPractice, practice_id)
        if not practice:
            raise RuntimeError("Text practice was deleted during synthesis.")
        # A user can edit or re-queue while a provider is generating. Recheck
        # immediately before any Material/Sentence/practice writes.
        try:
            _require_current_snapshot(practice, job_id=job_id, snapshot=snapshot)
        except TTSJobObsoleteError:
            _remove_obsolete_tts_outputs(output_dir, merged_path)
            raise
        if practice.material_id:
            old_sentences = session.exec(select(Sentence).where(Sentence.material_id == practice.material_id)).all()
            for old in old_sentences:
                session.delete(old)
            material = session.get(Material, practice.material_id)
        else:
            material = None
        content_language = str(snapshot["target_language"])
        translation_language = str(snapshot["translation_language"])
        if not material:
            material = Material(
                title=title,
                file_type="audio",
                original_path=str(merged_path),
                source_type="text_tts",
                content_language=content_language,
                translation_language=translation_language,
            )
            session.add(material)
            session.flush()
        else:
            material.original_path = str(merged_path)
            material.content_language = content_language
            material.translation_language = translation_language
        material.audio_path, material.duration, material.status = str(merged_path), total_duration, "ready"
        material.processing_stage, material.processing_progress, material.error_message = "completed", 100, None
        offset = 0.0
        for index, (sentence_text, translation, duration, clip_path) in enumerate(
            zip(sentences, translations, durations, paths),
            start=1,
        ):
            end = offset + duration
            session.add(Sentence(material_id=material.id, display_order=index, start_time=offset, end_time=end, original_start_time=offset, original_end_time=end, clip_audio_path=str(clip_path), clip_duration=duration, source_text=sentence_text, translation=translation))
            offset = end
        practice.tts_audio_path, practice.tts_status, practice.material_id = str(merged_path), "ready", material.id
        practice.updated_at = datetime.now(UTC)
        session.add(material); session.add(practice); session.commit(); session.refresh(material)
        return {"text_practice_id": practice_id, "material_id": material.id}
