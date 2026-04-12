import logging
import shutil
import subprocess
import uuid

from pathlib import Path
from typing import Any, Sequence

from fastapi import UploadFile

from app.core.config import settings


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
MIN_CLIP_DURATION_SECONDS = 0.05
DEFAULT_LEADING_PAD_MS = 100
DEFAULT_TRAILING_PAD_MS = 140

logger = logging.getLogger(__name__)


def _run_media_command(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


# Ensure necessary directories exist
def ensure_directories() -> None:
    for path in [
        settings.data_path,
        settings.materials_dir,
        settings.audio_dir,
        settings.sentence_audio_dir,
        settings.recordings_dir,
        settings.cache_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)

# Call this function at startup to create directories
async def save_upload(upload_file: UploadFile, target_dir: Path) -> Path:
    suffix = Path(upload_file.filename or "").suffix.lower()
    filename = f"{uuid.uuid4().hex}{suffix}"
    target_path = target_dir / filename
    with target_path.open("wb") as file_obj:
        shutil.copyfileobj(upload_file.file, file_obj)
    return target_path

# Media processing functions
def detect_file_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    return "unknown"

# For video files, extract audio and return the path to the audio file
def extract_audio(input_path: Path) -> Path:
    output_path = settings.audio_dir / f"{input_path.stem}.wav"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_path),
    ]
    _run_media_command(command)
    return output_path


def extract_audio_segment(
    input_audio_path: Path,
    output_audio_path: Path,
    start_time: float,
    end_time: float,
) -> None:
    safe_start = max(float(start_time), 0.0)
    safe_end = max(float(end_time), safe_start + MIN_CLIP_DURATION_SECONDS)
    output_audio_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_audio_path),
        "-ss",
        f"{safe_start:.6f}",
        "-to",
        f"{safe_end:.6f}",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_audio_path),
    ]
    _run_media_command(command)


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_original_sentence_bounds(item: dict[str, Any]) -> tuple[float, float]:
    start_time = max(float(item["start_time"]), 0.0)
    end_time = max(float(item["end_time"]), start_time + MIN_CLIP_DURATION_SECONDS)
    return start_time, end_time


def _extract_sentence_effective_word_bounds(
    item: dict[str, Any],
) -> tuple[float | None, float | None]:
    return _as_float(item.get("word_start_time")), _as_float(item.get("word_end_time"))


def _compute_trimmed_sentence_bounds(
    original_start_time: float,
    original_end_time: float,
    word_start_time: float | None,
    word_end_time: float | None,
    *,
    leading_pad_ms: float,
    trailing_pad_ms: float,
) -> tuple[float, float, bool, str]:
    safe_leading_pad = max(float(leading_pad_ms), 0.0) / 1000.0
    safe_trailing_pad = max(float(trailing_pad_ms), 0.0) / 1000.0

    normalized_word_start: float | None = None
    if word_start_time is not None:
        normalized_word_start = min(max(word_start_time, original_start_time), original_end_time)

    normalized_word_end: float | None = None
    if word_end_time is not None:
        normalized_word_end = min(max(word_end_time, original_start_time), original_end_time)

    if (
        normalized_word_start is not None
        and normalized_word_end is not None
        and normalized_word_end < normalized_word_start
    ):
        normalized_word_start = None
        normalized_word_end = None
        return original_start_time, original_end_time, False, "fallback_invalid_word_order"

    if normalized_word_start is None and normalized_word_end is None:
        return original_start_time, original_end_time, False, "fallback_no_word_bounds"

    trimmed_start_time = original_start_time
    if normalized_word_start is not None:
        trimmed_start_time = max(original_start_time, normalized_word_start - safe_leading_pad)

    trimmed_end_time = original_end_time
    if normalized_word_end is not None:
        trimmed_end_time = min(original_end_time, normalized_word_end + safe_trailing_pad)

    if trimmed_end_time < trimmed_start_time + MIN_CLIP_DURATION_SECONDS:
        return original_start_time, original_end_time, False, "fallback_invalid_trim_window"

    return trimmed_start_time, trimmed_end_time, True, "trimmed_using_word_bounds"


def _log_sentence_clip_bounds(
    *,
    display_order: int,
    original_start_time: float,
    original_end_time: float,
    word_start_time: float | None,
    word_end_time: float | None,
    clip_start_time: float,
    clip_end_time: float,
    used_trimmed_bounds: bool,
    trim_reason: str,
) -> None:
    logger.debug(
        (
            "Sentence clip bounds: order=%s original=(%.3f, %.3f) "
            "word=(%s, %s) clip=(%.3f, %.3f) trimmed=%s reason=%s"
        ),
        display_order,
        original_start_time,
        original_end_time,
        "None" if word_start_time is None else f"{word_start_time:.3f}",
        "None" if word_end_time is None else f"{word_end_time:.3f}",
        clip_start_time,
        clip_end_time,
        used_trimmed_bounds,
        trim_reason,
    )


def build_sentence_audio_metadata(
    input_audio_path: Path,
    material_id: int,
    sentence_candidates: Sequence[dict[str, Any]],
    leading_pad_ms: float = DEFAULT_LEADING_PAD_MS,
    trailing_pad_ms: float = DEFAULT_TRAILING_PAD_MS,
) -> list[dict[str, Any]]:
    material_segment_dir = settings.sentence_audio_dir / f"material_{material_id}"
    if material_segment_dir.exists():
        shutil.rmtree(material_segment_dir)
    material_segment_dir.mkdir(parents=True, exist_ok=True)

    enriched_sentences: list[dict[str, Any]] = []
    for item in sentence_candidates:
        start_time, end_time = _extract_original_sentence_bounds(item)
        word_start_time, word_end_time = _extract_sentence_effective_word_bounds(item)
        clip_start_time, clip_end_time, used_trimmed_bounds, trim_reason = _compute_trimmed_sentence_bounds(
            start_time,
            end_time,
            word_start_time,
            word_end_time,
            leading_pad_ms=leading_pad_ms,
            trailing_pad_ms=trailing_pad_ms,
        )
        display_order = int(item["display_order"])
        clip_path = material_segment_dir / f"{display_order:04d}.wav"

        _log_sentence_clip_bounds(
            display_order=display_order,
            original_start_time=start_time,
            original_end_time=end_time,
            word_start_time=word_start_time,
            word_end_time=word_end_time,
            clip_start_time=clip_start_time,
            clip_end_time=clip_end_time,
            used_trimmed_bounds=used_trimmed_bounds,
            trim_reason=trim_reason,
        )

        extract_audio_segment(
            input_audio_path=input_audio_path,
            output_audio_path=clip_path,
            start_time=clip_start_time,
            end_time=clip_end_time,
        )
        clip_duration = get_audio_duration(clip_path)

        enriched = dict(item)
        enriched["original_start_time"] = start_time
        enriched["original_end_time"] = end_time
        enriched["clip_start_time"] = clip_start_time
        enriched["clip_end_time"] = clip_end_time
        enriched["clip_trimmed"] = used_trimmed_bounds
        enriched["clip_trim_reason"] = trim_reason
        enriched["clip_audio_path"] = str(clip_path)
        enriched["clip_duration"] = clip_duration
        enriched_sentences.append(enriched)

    return enriched_sentences


# For audio files, convert to WAV format if necessary and return the path to the WAV file
def get_audio_duration(file_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nokey=1:noprint_wrappers=1",
        str(file_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())
