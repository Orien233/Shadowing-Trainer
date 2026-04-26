from pathlib import Path

from app.core.config import settings
from app.schemas.system import FileCleanupError, RecordingCleanupResponse

RECORDING_FILE_EXTENSIONS = {".webm", ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}


def list_recording_files() -> list[Path]:
    recordings_dir = settings.recordings_dir
    if not recordings_dir.exists():
        return []
    return [
        path
        for path in recordings_dir.iterdir()
        if path.is_file() and path.suffix.lower() in RECORDING_FILE_EXTENSIONS
    ]


def cleanup_recording_files() -> RecordingCleanupResponse:
    files = list_recording_files()
    failed_files: list[FileCleanupError] = []
    deleted_files = 0

    for path in files:
        try:
            path.unlink()
            deleted_files += 1
        except OSError as exc:
            failed_files.append(FileCleanupError(path=str(path), reason=str(exc)))

    return RecordingCleanupResponse(
        target_dir=str(settings.recordings_dir),
        total_files=len(files),
        deleted_files=deleted_files,
        failed_files=failed_files,
    )
