import shutil
import subprocess
import uuid

from pathlib import Path
from fastapi import UploadFile
from app.core.config import settings


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

# Ensure necessary directories exist
def ensure_directories() -> None:
    for path in [
        settings.data_path,
        settings.materials_dir,
        settings.audio_dir,
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
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path

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
