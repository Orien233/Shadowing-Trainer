import shutil
import subprocess
import uuid

from pathlib import Path
from typing import Any, Sequence

from fastapi import UploadFile

from app.core.config import settings


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


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
    safe_end = max(float(end_time), safe_start + 0.05)
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


def build_sentence_audio_metadata(
    input_audio_path: Path,
    material_id: int,
    sentence_candidates: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    material_segment_dir = settings.sentence_audio_dir / f"material_{material_id}"
    if material_segment_dir.exists():
        shutil.rmtree(material_segment_dir)
    material_segment_dir.mkdir(parents=True, exist_ok=True)

    enriched_sentences: list[dict[str, Any]] = []
    for item in sentence_candidates:
        start_time = max(float(item["start_time"]), 0.0)
        end_time = max(float(item["end_time"]), start_time + 0.05)
        display_order = int(item["display_order"])
        clip_path = material_segment_dir / f"{display_order:04d}.wav"

        extract_audio_segment(
            input_audio_path=input_audio_path,
            output_audio_path=clip_path,
            start_time=start_time,
            end_time=end_time,
        )
        clip_duration = get_audio_duration(clip_path)

        enriched = dict(item)
        enriched["original_start_time"] = start_time
        enriched["original_end_time"] = end_time
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
