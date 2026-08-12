"""Optional, process-local runtime for faster-whisper.

Remote-only installations must be able to import and start the application
without the local Whisper extra installed.  This module therefore never imports
``faster_whisper`` until a transcription or an explicit model-load check asks
for it.
"""

from __future__ import annotations

import gc
import importlib.util
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings


class LocalWhisperUnavailableError(RuntimeError):
    """Raised when a local ASR route is selected but cannot run."""


@dataclass(frozen=True)
class LocalWhisperStatus:
    installed: bool
    runtime_ready: bool
    model_loaded: bool
    model_cached: bool
    will_download_on_first_use: bool
    model_name: str
    device: str
    compute_type: str
    model_dir: str
    allow_download: bool
    error: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


_model_lock = threading.RLock()
_model: Any | None = None


def _is_installed() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def _model_directory() -> Path:
    return settings.whisper_model_path


def _is_model_cached(model_dir: Path, model_name: str) -> bool:
    """Best-effort cache inspection without importing Hugging Face packages."""
    candidate = Path(model_name)
    if candidate.is_dir():
        return True
    if (model_dir / model_name).is_dir():
        return True
    normalized = model_name.removeprefix("Systran/").replace("/", "--")
    cache_prefixes = (
        f"models--Systran--faster-whisper-{normalized}",
        f"models--{normalized}",
        f"faster-whisper-{normalized}",
    )
    try:
        return any(
            entry.is_dir() and entry.name.startswith(cache_prefixes)
            for entry in model_dir.iterdir()
        )
    except OSError:
        return False


def _device_error(device: str) -> str | None:
    normalized = device.strip().lower()
    if normalized in {"cpu", "auto"}:
        return None
    if normalized != "cuda":
        return f"Unsupported Local Whisper device '{device}'. Use cpu, cuda, or auto."
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() < 1:
            return "CUDA is selected but no CUDA device is available to CTranslate2."
    except Exception as exc:
        return f"CUDA validation failed: {type(exc).__name__}."
    return None


def get_local_whisper_status() -> LocalWhisperStatus:
    """Return a no-download/no-model-load readiness report."""
    with _model_lock:
        loaded = _model is not None
    model_dir = _model_directory()
    installed = _is_installed()
    if not installed:
        return LocalWhisperStatus(
            installed=False,
            runtime_ready=False,
            model_loaded=loaded,
            model_cached=False,
            will_download_on_first_use=False,
            model_name=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            model_dir=str(model_dir),
            allow_download=settings.whisper_allow_download,
            error="Local Whisper is not installed. Install backend/requirements-local-whisper.txt to enable it.",
        )
    device_error = _device_error(settings.whisper_device)
    cached = _is_model_cached(model_dir, settings.whisper_model)
    offline_model_error = (
        "The configured Local Whisper model is not cached and runtime downloads are disabled."
        if device_error is None and not cached and not loaded and not settings.whisper_allow_download
        else None
    )
    error = device_error or offline_model_error
    return LocalWhisperStatus(
        installed=True,
        runtime_ready=error is None,
        model_loaded=loaded,
        model_cached=cached or loaded,
        will_download_on_first_use=not cached and not loaded and settings.whisper_allow_download and error is None,
        model_name=settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        model_dir=str(model_dir),
        allow_download=settings.whisper_allow_download,
        error=error,
    )


def load_local_whisper_model() -> Any:
    """Load once, respecting the configured download policy."""
    global _model
    with _model_lock:
        if _model is not None:
            return _model
        status = get_local_whisper_status()
        if not status.installed or not status.runtime_ready:
            raise LocalWhisperUnavailableError(status.error or "Local Whisper is unavailable.")
        try:
            from faster_whisper import WhisperModel

            model_dir = _model_directory()
            model_dir.mkdir(parents=True, exist_ok=True)
            _model = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
                download_root=str(model_dir),
                local_files_only=not settings.whisper_allow_download,
            )
            return _model
        except Exception as exc:
            _model = None
            if not settings.whisper_allow_download and not status.model_cached:
                raise LocalWhisperUnavailableError(
                    "The configured Local Whisper model is not cached and runtime downloads are disabled. "
                    "Install/cache the model first or enable WHISPER_ALLOW_DOWNLOAD."
                ) from exc
            raise LocalWhisperUnavailableError(
                f"Local Whisper could not load model '{settings.whisper_model}': {type(exc).__name__}."
            ) from exc


def release_local_whisper_model() -> LocalWhisperStatus:
    """Release the cached model safely after the current caller finishes."""
    global _model
    with _model_lock:
        _model = None
    gc.collect()
    return get_local_whisper_status()


__all__ = [
    "LocalWhisperStatus",
    "LocalWhisperUnavailableError",
    "get_local_whisper_status",
    "load_local_whisper_model",
    "release_local_whisper_model",
]
