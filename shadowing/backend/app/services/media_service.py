import logging
import os
import subprocess
import uuid

from pathlib import Path
from typing import Any, Sequence

from fastapi import UploadFile

from app.core.config import settings


VIDEO_MAX_BYTES = 150 * 1024 * 1024
VIDEO_TARGET_BYTES = 145 * 1024 * 1024
VIDEO_AUDIO_BITRATE_KBPS = 128
VIDEO_MIN_BITRATE_KBPS = 300
MIN_CLIP_DURATION_SECONDS = 0.05
DEFAULT_LEADING_PAD_MS = 100
DEFAULT_TRAILING_PAD_MS = 140
DEFAULT_TRAILING_TAIL_PROTECT_MS = 300
DEFAULT_NEXT_SENTENCE_GUARD_MS = 20

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
        settings.videos_dir,
        settings.cache_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)

# Call this function at startup to create directories
async def save_upload(
    upload_file: UploadFile,
    target_dir: Path,
    *,
    max_bytes: int | None = None,
) -> Path:
    """Stream an upload into a temporary file and never keep rejected input."""
    suffix = Path(upload_file.filename or "").suffix.lower()
    filename = f"{uuid.uuid4().hex}{suffix}"
    target_path = target_dir / filename
    temporary_path = target_path.with_suffix(f"{target_path.suffix}.part")
    target_dir.mkdir(parents=True, exist_ok=True)
    received = 0
    try:
        with temporary_path.open("wb") as file_obj:
            while chunk := await upload_file.read(1024 * 1024):
                received += len(chunk)
                if max_bytes is not None and received > max_bytes:
                    raise ValueError("Upload exceeds the allowed file size.")
                file_obj.write(chunk)
        temporary_path.replace(target_path)
        return target_path
    except Exception:
        temporary_path.unlink(missing_ok=True)
        target_path.unlink(missing_ok=True)
        raise
    finally:
        await upload_file.close()

# Media processing functions
def _probe_media_stream_types(file_path: Path) -> set[str]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "default=nokey=1:noprint_wrappers=1",
        str(file_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except Exception:
        return set()

    return {line.strip().lower() for line in result.stdout.splitlines() if line.strip()}


def detect_file_type(file_path: Path) -> str:
    stream_types = _probe_media_stream_types(file_path)
    if "video" in stream_types:
        return "video"
    if "audio" in stream_types:
        return "audio"

    return "unknown"


def transcode_video_for_storage(source_video_path: Path) -> Path:
    """Create a bounded MP4 before any audio extraction occurs.

    The first pass calculates video frames only.  The second pass retains a
    128 kbps AAC track and reserves container headroom below the 150 MiB cap.
    """
    duration = get_audio_duration(source_video_path)
    if duration <= 0:
        raise ValueError("Video duration is invalid.")
    total_kbps = (VIDEO_TARGET_BYTES * 8 / duration) / 1000
    video_kbps = int(total_kbps - VIDEO_AUDIO_BITRATE_KBPS)
    if video_kbps < VIDEO_MIN_BITRATE_KBPS:
        raise ValueError("Video is too long to fit within 150 MiB at the minimum quality.")

    output_path = settings.videos_dir / f"{uuid.uuid4().hex}.mp4"
    passlog = settings.cache_dir / f"video-pass-{uuid.uuid4().hex}"
    common = [
        "ffmpeg", "-y", "-i", str(source_video_path), "-map", "0:v:0",
        "-c:v", "libx264", "-b:v", f"{video_kbps}k", "-maxrate", f"{video_kbps}k",
        "-bufsize", f"{video_kbps * 2}k", "-pix_fmt", "yuv420p", "-preset", "medium",
        "-passlogfile", str(passlog),
    ]
    try:
        _run_media_command([*common, "-pass", "1", "-an", "-f", "mp4", os.devnull])
        _run_media_command([
            *common, "-pass", "2", "-map", "0:a:0?", "-c:a", "aac",
            "-b:a", f"{VIDEO_AUDIO_BITRATE_KBPS}k", "-movflags", "+faststart", str(output_path),
        ])
        if output_path.stat().st_size > VIDEO_MAX_BYTES:
            raise ValueError("Transcoded video exceeds the 150 MiB limit.")
        return output_path
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    finally:
        for candidate in settings.cache_dir.glob(f"{passlog.name}*"):
            candidate.unlink(missing_ok=True)

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
    source_audio_duration: float | None = None,
) -> None:
    if source_audio_duration is None:
        safe_start = max(float(start_time), 0.0)
        safe_end = max(float(end_time), safe_start + MIN_CLIP_DURATION_SECONDS)
    else:
        safe_media_duration = max(float(source_audio_duration), 0.0)
        safe_start, safe_end = _clamp_bounds_to_media_duration(
            start_time,
            end_time,
            media_duration=safe_media_duration,
        )
        if safe_end <= safe_start and safe_start < safe_media_duration:
            safe_end = min(
                safe_media_duration,
                safe_start + min(MIN_CLIP_DURATION_SECONDS, safe_media_duration),
            )

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


def _clamp_bounds_to_media_duration(
    start_time: float,
    end_time: float,
    *,
    media_duration: float,
) -> tuple[float, float]:
    safe_media_duration = max(float(media_duration), 0.0)
    safe_start_time = min(max(float(start_time), 0.0), safe_media_duration)
    safe_end_time = min(max(float(end_time), safe_start_time), safe_media_duration)
    return safe_start_time, safe_end_time


def _expand_bounds_to_min_duration(
    start_time: float,
    end_time: float,
    *,
    media_duration: float,
) -> tuple[float, float]:
    safe_media_duration = max(float(media_duration), 0.0)
    if safe_media_duration <= 0.0:
        return 0.0, 0.0

    min_required_duration = min(MIN_CLIP_DURATION_SECONDS, safe_media_duration)
    if end_time - start_time >= min_required_duration:
        return start_time, end_time

    expanded_end_time = min(start_time + min_required_duration, safe_media_duration)
    if expanded_end_time - start_time >= min_required_duration:
        return start_time, expanded_end_time

    expanded_start_time = max(0.0, end_time - min_required_duration)
    return expanded_start_time, end_time


def _extract_original_sentence_bounds(
    item: dict[str, Any],
    *,
    media_duration: float,
) -> tuple[float, float]:
    start_time = max(float(item["start_time"]), 0.0)
    end_time = max(float(item["end_time"]), start_time + MIN_CLIP_DURATION_SECONDS)
    clamped_start_time, clamped_end_time = _clamp_bounds_to_media_duration(
        start_time,
        end_time,
        media_duration=media_duration,
    )
    return _expand_bounds_to_min_duration(
        clamped_start_time,
        clamped_end_time,
        media_duration=media_duration,
    )


def _extract_sentence_start_time(item: dict[str, Any], *, media_duration: float) -> float:
    safe_media_duration = max(float(media_duration), 0.0)
    return min(max(float(item["start_time"]), 0.0), safe_media_duration)


def _extract_sentence_effective_word_bounds(
    item: dict[str, Any],
) -> tuple[float | None, float | None]:
    return _as_float(item.get("word_start_time")), _as_float(item.get("word_end_time"))


def _compute_clip_end_soft_limit(
    original_end_time: float,
    next_sentence_start_time: float | None,
    *,
    media_duration: float,
    trailing_tail_protect_ms: float,
    next_sentence_guard_ms: float,
) -> float:
    safe_media_duration = max(float(media_duration), 0.0)
    trailing_tail_protect_seconds = max(float(trailing_tail_protect_ms), 0.0) / 1000.0
    clip_end_soft_limit = original_end_time + trailing_tail_protect_seconds

    if next_sentence_start_time is None:
        return min(max(clip_end_soft_limit, original_end_time), safe_media_duration)

    next_sentence_guard_seconds = max(float(next_sentence_guard_ms), 0.0) / 1000.0
    guarded_next_sentence_start = max(next_sentence_start_time - next_sentence_guard_seconds, 0.0)
    bounded_clip_end_soft_limit = max(original_end_time, min(clip_end_soft_limit, guarded_next_sentence_start))
    return min(bounded_clip_end_soft_limit, safe_media_duration)


def _compute_trimmed_sentence_bounds(
    original_start_time: float,
    original_end_time: float,
    clip_end_soft_limit: float,
    word_start_time: float | None,
    word_end_time: float | None,
    *,
    media_duration: float,
    leading_pad_ms: float,
    trailing_pad_ms: float,
) -> tuple[float, float, bool, str]:
    safe_leading_pad = max(float(leading_pad_ms), 0.0) / 1000.0
    safe_trailing_pad = max(float(trailing_pad_ms), 0.0) / 1000.0
    fallback_start_time, fallback_end_time = _expand_bounds_to_min_duration(
        *_clamp_bounds_to_media_duration(
            original_start_time,
            original_end_time,
            media_duration=media_duration,
        ),
        media_duration=media_duration,
    )

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
        return fallback_start_time, fallback_end_time, False, "fallback_invalid_word_order"

    if normalized_word_start is None and normalized_word_end is None:
        return fallback_start_time, fallback_end_time, False, "fallback_no_word_bounds"

    trimmed_start_time = original_start_time
    if normalized_word_start is not None:
        trimmed_start_time = max(original_start_time, normalized_word_start - safe_leading_pad)

    trimmed_end_time = original_end_time
    if normalized_word_end is not None:
        safe_clip_end_soft_limit = max(clip_end_soft_limit, original_end_time)
        trimmed_end_time = min(safe_clip_end_soft_limit, normalized_word_end + safe_trailing_pad)

    trimmed_start_time, trimmed_end_time = _clamp_bounds_to_media_duration(
        trimmed_start_time,
        trimmed_end_time,
        media_duration=media_duration,
    )
    if trimmed_end_time < trimmed_start_time + MIN_CLIP_DURATION_SECONDS:
        return fallback_start_time, fallback_end_time, False, "fallback_invalid_trim_window"

    return trimmed_start_time, trimmed_end_time, True, "trimmed_using_word_bounds"


def _log_sentence_clip_bounds(
    *,
    display_order: int,
    original_start_time: float,
    original_end_time: float,
    clip_end_soft_limit: float,
    next_sentence_start_time: float | None,
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
            "word=(%s, %s) next_start=%s soft_limit=%.3f "
            "clip=(%.3f, %.3f) trimmed=%s reason=%s"
        ),
        display_order,
        original_start_time,
        original_end_time,
        "None" if word_start_time is None else f"{word_start_time:.3f}",
        "None" if word_end_time is None else f"{word_end_time:.3f}",
        "None" if next_sentence_start_time is None else f"{next_sentence_start_time:.3f}",
        clip_end_soft_limit,
        clip_start_time,
        clip_end_time,
        used_trimmed_bounds,
        trim_reason,
    )


def _append_trim_reason(trim_reason: str, suffix: str) -> str:
    if not trim_reason:
        return suffix

    tokens = trim_reason.split("|")
    if suffix in tokens:
        return trim_reason
    return f"{trim_reason}|{suffix}"


def _enforce_non_overlapping_clip_bounds(
    clip_windows: list[dict[str, Any]],
    *,
    media_duration: float,
) -> None:
    if len(clip_windows) < 2:
        return

    safe_media_duration = max(float(media_duration), 0.0)
    min_required_duration = min(MIN_CLIP_DURATION_SECONDS, safe_media_duration)

    for index in range(len(clip_windows) - 1):
        current_window = clip_windows[index]
        next_window = clip_windows[index + 1]

        current_start, current_end = _clamp_bounds_to_media_duration(
            current_window["clip_start_time"],
            current_window["clip_end_time"],
            media_duration=safe_media_duration,
        )
        next_start, next_end = _clamp_bounds_to_media_duration(
            next_window["clip_start_time"],
            next_window["clip_end_time"],
            media_duration=safe_media_duration,
        )

        current_window["clip_start_time"] = current_start
        current_window["clip_end_time"] = current_end
        next_window["clip_start_time"] = next_start
        next_window["clip_end_time"] = next_end

        if current_end <= next_start:
            continue

        boundary = next_start
        current_min_end = min(current_start + min_required_duration, safe_media_duration)
        next_max_start = max(next_end - min_required_duration, 0.0)

        if boundary < current_min_end:
            boundary = current_min_end
        if boundary > next_max_start:
            boundary = next_max_start

        boundary = min(max(boundary, current_start), next_end)

        if boundary < current_end:
            current_window["clip_end_time"] = boundary
            current_window["clip_trimmed"] = True
            current_window["clip_trim_reason"] = _append_trim_reason(
                current_window["clip_trim_reason"],
                "non_overlap_capped_to_next",
            )
        if boundary > next_start:
            next_window["clip_start_time"] = boundary
            next_window["clip_trimmed"] = True
            next_window["clip_trim_reason"] = _append_trim_reason(
                next_window["clip_trim_reason"],
                "non_overlap_shifted_after_prev",
            )

    previous_end = 0.0
    for window in clip_windows:
        normalized_start = min(
            max(float(window["clip_start_time"]), previous_end),
            safe_media_duration,
        )
        normalized_end = min(
            max(float(window["clip_end_time"]), normalized_start),
            safe_media_duration,
        )
        if (
            min_required_duration > 0.0
            and normalized_start < safe_media_duration
            and normalized_end - normalized_start < min_required_duration
        ):
            min_feasible_end = min(normalized_start + min_required_duration, safe_media_duration)
            if min_feasible_end > normalized_end:
                normalized_end = min_feasible_end
                window["clip_trimmed"] = True
                window["clip_trim_reason"] = _append_trim_reason(
                    window["clip_trim_reason"],
                    "non_overlap_min_duration_enforced",
                )
        window["clip_start_time"] = normalized_start
        window["clip_end_time"] = normalized_end
        previous_end = normalized_end


def build_sentence_audio_metadata(
    input_audio_path: Path,
    material_id: int,
    sentence_candidates: Sequence[dict[str, Any]],
    source_audio_duration: float | None = None,
    leading_pad_ms: float = DEFAULT_LEADING_PAD_MS,
    trailing_pad_ms: float = DEFAULT_TRAILING_PAD_MS,
    trailing_tail_protect_ms: float = DEFAULT_TRAILING_TAIL_PROTECT_MS,
    next_sentence_guard_ms: float = DEFAULT_NEXT_SENTENCE_GUARD_MS,
    apply_trim_to_sentence_time_fields: bool = True,
) -> list[dict[str, Any]]:
    if source_audio_duration is None:
        source_audio_duration = get_audio_duration(input_audio_path)
    media_duration_limit = max(float(source_audio_duration), 0.0)

    material_segment_dir = settings.sentence_audio_dir / f"material_{material_id}"
    if material_segment_dir.exists():
        shutil.rmtree(material_segment_dir)
    material_segment_dir.mkdir(parents=True, exist_ok=True)

    prepared_windows: list[dict[str, Any]] = []
    for index, item in enumerate(sentence_candidates):
        start_time, end_time = _extract_original_sentence_bounds(
            item,
            media_duration=media_duration_limit,
        )
        word_start_time, word_end_time = _extract_sentence_effective_word_bounds(item)
        next_sentence_start_time: float | None = None
        if index + 1 < len(sentence_candidates):
            next_sentence_start_time = _extract_sentence_start_time(
                sentence_candidates[index + 1],
                media_duration=media_duration_limit,
            )
        clip_end_soft_limit = _compute_clip_end_soft_limit(
            end_time,
            next_sentence_start_time,
            media_duration=media_duration_limit,
            trailing_tail_protect_ms=trailing_tail_protect_ms,
            next_sentence_guard_ms=next_sentence_guard_ms,
        )
        clip_start_time, clip_end_time, used_trimmed_bounds, trim_reason = _compute_trimmed_sentence_bounds(
            start_time,
            end_time,
            clip_end_soft_limit,
            word_start_time,
            word_end_time,
            media_duration=media_duration_limit,
            leading_pad_ms=leading_pad_ms,
            trailing_pad_ms=trailing_pad_ms,
        )
        display_order = int(item["display_order"])
        clip_path = material_segment_dir / f"{display_order:04d}.wav"

        prepared_windows.append(
            {
                "item": item,
                "display_order": display_order,
                "original_start_time": start_time,
                "original_end_time": end_time,
                "next_sentence_start_time": next_sentence_start_time,
                "clip_end_soft_limit": clip_end_soft_limit,
                "word_start_time": word_start_time,
                "word_end_time": word_end_time,
                "clip_start_time": clip_start_time,
                "clip_end_time": clip_end_time,
                "clip_trimmed": used_trimmed_bounds,
                "clip_trim_reason": trim_reason,
                "clip_path": clip_path,
            }
        )

    _enforce_non_overlapping_clip_bounds(
        prepared_windows,
        media_duration=media_duration_limit,
    )

    enriched_sentences: list[dict[str, Any]] = []
    for window in prepared_windows:
        item = window["item"]
        _log_sentence_clip_bounds(
            display_order=window["display_order"],
            original_start_time=window["original_start_time"],
            original_end_time=window["original_end_time"],
            clip_end_soft_limit=window["clip_end_soft_limit"],
            next_sentence_start_time=window["next_sentence_start_time"],
            word_start_time=window["word_start_time"],
            word_end_time=window["word_end_time"],
            clip_start_time=window["clip_start_time"],
            clip_end_time=window["clip_end_time"],
            used_trimmed_bounds=bool(window["clip_trimmed"]),
            trim_reason=window["clip_trim_reason"],
        )

        extract_audio_segment(
            input_audio_path=input_audio_path,
            output_audio_path=window["clip_path"],
            start_time=window["clip_start_time"],
            end_time=window["clip_end_time"],
            source_audio_duration=media_duration_limit,
        )
        clip_duration = get_audio_duration(window["clip_path"])

        enriched = dict(item)
        if apply_trim_to_sentence_time_fields:
            enriched["start_time"] = window["clip_start_time"]
            enriched["end_time"] = window["clip_end_time"]

        enriched["original_start_time"] = window["original_start_time"]
        enriched["original_end_time"] = window["original_end_time"]
        enriched["clip_start_time"] = window["clip_start_time"]
        enriched["clip_end_time"] = window["clip_end_time"]
        enriched["clip_trimmed"] = bool(window["clip_trimmed"])
        enriched["clip_trim_reason"] = window["clip_trim_reason"]
        enriched["clip_audio_path"] = str(window["clip_path"])
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
