from __future__ import annotations

import logging
import uuid

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf


logger = logging.getLogger(__name__)
LIBROSA_SPLIT_METHOD = "librosa_split"
TRIMMED_AUDIO_SUBDIR = "trimmed_recordings"


@dataclass
class SpeechSpanDetection:
    """Detected active speech span and normalized VAD metadata."""

    waveform: np.ndarray
    sample_rate: int
    total_samples: int
    start_sample: int
    end_sample: int
    metadata: dict[str, Any]
    tags: tuple[str, ...]
    used_fallback: bool


@dataclass(frozen=True)
class TrimmedAudioResult:
    """Result of trimming operation for downstream evaluation."""

    audio_path: str
    metadata: dict[str, Any]
    tags: tuple[str, ...]
    should_cleanup: bool


def _seconds(sample_count: int, sample_rate: int) -> float:
    if sample_rate <= 0:
        return 0.0
    return float(sample_count / float(sample_rate))


def _rounded_seconds(value: float) -> float:
    return round(max(float(value), 0.0), 6)


def _build_metadata(
    *,
    sample_rate: int,
    start_sample: int,
    end_sample: int,
    total_samples: int,
    pad_sec: float,
    top_db: float,
    frame_length: int,
    hop_length: int,
    used_fallback: bool,
    fallback_reason: str | None,
) -> dict[str, Any]:
    original_duration_sec = _seconds(total_samples, sample_rate)
    trimmed_samples = max(end_sample - start_sample, 0)
    trimmed_duration_sec = _seconds(trimmed_samples, sample_rate)
    return {
        "method": LIBROSA_SPLIT_METHOD,
        "start_sec": _rounded_seconds(_seconds(start_sample, sample_rate)),
        "end_sec": _rounded_seconds(_seconds(end_sample, sample_rate)),
        "original_duration_sec": _rounded_seconds(original_duration_sec),
        "trimmed_duration_sec": _rounded_seconds(trimmed_duration_sec),
        "padding_sec": _rounded_seconds(pad_sec),
        "top_db": float(top_db),
        "frame_length": int(frame_length),
        "hop_length": int(hop_length),
        "sample_rate": int(sample_rate),
        "used_fallback": bool(used_fallback),
        "fallback_reason": fallback_reason,
    }


def detect_active_speech_span(
    audio_path: str | Path,
    *,
    sample_rate: int = 16000,
    top_db: float = 30.0,
    frame_length: int = 1024,
    hop_length: int = 256,
    pad_sec: float = 0.20,
) -> SpeechSpanDetection:
    """Detect active speech span from first to last non-silent interval.

    The function is intentionally lightweight and backend-agnostic so it can be
    replaced by a stronger VAD engine in a later phase.
    """
    normalized_pad_sec = max(float(pad_sec), 0.0)

    try:
        waveform, loaded_sr = librosa.load(
            str(audio_path),
            sr=int(sample_rate),
            mono=True,
        )
        mono_waveform = np.asarray(waveform, dtype=np.float32)
        resolved_sr = int(loaded_sr)
    except Exception as exc:
        logger.warning("Failed loading learner audio for trim: %s", exc)
        metadata = _build_metadata(
            sample_rate=int(sample_rate),
            start_sample=0,
            end_sample=0,
            total_samples=0,
            pad_sec=normalized_pad_sec,
            top_db=top_db,
            frame_length=frame_length,
            hop_length=hop_length,
            used_fallback=True,
            fallback_reason=f"audio_load_error:{type(exc).__name__}",
        )
        return SpeechSpanDetection(
            waveform=np.asarray([], dtype=np.float32),
            sample_rate=int(sample_rate),
            total_samples=0,
            start_sample=0,
            end_sample=0,
            metadata=metadata,
            tags=tuple(),
            used_fallback=True,
        )

    total_samples = int(mono_waveform.size)
    if total_samples == 0:
        metadata = _build_metadata(
            sample_rate=resolved_sr,
            start_sample=0,
            end_sample=0,
            total_samples=0,
            pad_sec=normalized_pad_sec,
            top_db=top_db,
            frame_length=frame_length,
            hop_length=hop_length,
            used_fallback=True,
            fallback_reason="empty_audio",
        )
        return SpeechSpanDetection(
            waveform=mono_waveform,
            sample_rate=resolved_sr,
            total_samples=0,
            start_sample=0,
            end_sample=0,
            metadata=metadata,
            tags=tuple(),
            used_fallback=True,
        )

    try:
        intervals = librosa.effects.split(
            mono_waveform,
            top_db=float(top_db),
            frame_length=int(frame_length),
            hop_length=int(hop_length),
        )
    except Exception as exc:
        logger.warning("Failed detecting non-silent intervals for trim: %s", exc)
        metadata = _build_metadata(
            sample_rate=resolved_sr,
            start_sample=0,
            end_sample=total_samples,
            total_samples=total_samples,
            pad_sec=normalized_pad_sec,
            top_db=top_db,
            frame_length=frame_length,
            hop_length=hop_length,
            used_fallback=True,
            fallback_reason=f"split_error:{type(exc).__name__}",
        )
        return SpeechSpanDetection(
            waveform=mono_waveform,
            sample_rate=resolved_sr,
            total_samples=total_samples,
            start_sample=0,
            end_sample=total_samples,
            metadata=metadata,
            tags=tuple(),
            used_fallback=True,
        )

    if len(intervals) == 0:
        metadata = _build_metadata(
            sample_rate=resolved_sr,
            start_sample=0,
            end_sample=total_samples,
            total_samples=total_samples,
            pad_sec=normalized_pad_sec,
            top_db=top_db,
            frame_length=frame_length,
            hop_length=hop_length,
            used_fallback=True,
            fallback_reason="no_non_silent_interval",
        )
        return SpeechSpanDetection(
            waveform=mono_waveform,
            sample_rate=resolved_sr,
            total_samples=total_samples,
            start_sample=0,
            end_sample=total_samples,
            metadata=metadata,
            tags=tuple(),
            used_fallback=True,
        )

    pad_samples = int(round(normalized_pad_sec * float(resolved_sr)))
    raw_start_sample = int(intervals[0][0])
    raw_end_sample = int(intervals[-1][1])
    start_sample = max(raw_start_sample - pad_samples, 0)
    end_sample = min(raw_end_sample + pad_samples, total_samples)

    if end_sample <= start_sample:
        metadata = _build_metadata(
            sample_rate=resolved_sr,
            start_sample=0,
            end_sample=total_samples,
            total_samples=total_samples,
            pad_sec=normalized_pad_sec,
            top_db=top_db,
            frame_length=frame_length,
            hop_length=hop_length,
            used_fallback=True,
            fallback_reason="invalid_span_after_padding",
        )
        return SpeechSpanDetection(
            waveform=mono_waveform,
            sample_rate=resolved_sr,
            total_samples=total_samples,
            start_sample=0,
            end_sample=total_samples,
            metadata=metadata,
            tags=tuple(),
            used_fallback=True,
        )

    tags: list[str] = []
    if start_sample > 0:
        tags.append("trimmed_leading_silence")
    if end_sample < total_samples:
        tags.append("trimmed_trailing_silence")

    metadata = _build_metadata(
        sample_rate=resolved_sr,
        start_sample=start_sample,
        end_sample=end_sample,
        total_samples=total_samples,
        pad_sec=normalized_pad_sec,
        top_db=top_db,
        frame_length=frame_length,
        hop_length=hop_length,
        used_fallback=False,
        fallback_reason=None,
    )
    return SpeechSpanDetection(
        waveform=mono_waveform,
        sample_rate=resolved_sr,
        total_samples=total_samples,
        start_sample=start_sample,
        end_sample=end_sample,
        metadata=metadata,
        tags=tuple(tags),
        used_fallback=False,
    )


def _build_fallback_result(
    *,
    source_audio_path: Path,
    metadata: dict[str, Any],
    tags: tuple[str, ...],
    fallback_reason: str | None = None,
) -> TrimmedAudioResult:
    fallback_metadata = dict(metadata)
    fallback_metadata["used_fallback"] = True
    if fallback_reason is not None:
        fallback_metadata["fallback_reason"] = fallback_reason
    elif not fallback_metadata.get("fallback_reason"):
        fallback_metadata["fallback_reason"] = "trim_fallback"

    merged_tags = list(tags)
    if "trim_fallback_used" not in merged_tags:
        merged_tags.append("trim_fallback_used")
    return TrimmedAudioResult(
        audio_path=str(source_audio_path),
        metadata=fallback_metadata,
        tags=tuple(merged_tags),
        should_cleanup=False,
    )


def create_trimmed_audio(
    audio_path: str | Path,
    *,
    enabled: bool = True,
    sample_rate: int = 16000,
    top_db: float = 30.0,
    frame_length: int = 1024,
    hop_length: int = 256,
    pad_sec: float = 0.20,
    min_duration_sec: float = 0.30,
    cache_dir: str | Path | None = None,
) -> TrimmedAudioResult:
    """Create a temporary trimmed audio file and return path+metadata.

    Falls back to the original audio path when trimming is disabled or invalid.
    """
    source_audio_path = Path(audio_path)
    if not enabled:
        disabled_metadata = _build_metadata(
            sample_rate=int(sample_rate),
            start_sample=0,
            end_sample=0,
            total_samples=0,
            pad_sec=max(float(pad_sec), 0.0),
            top_db=top_db,
            frame_length=frame_length,
            hop_length=hop_length,
            used_fallback=True,
            fallback_reason="trim_disabled",
        )
        return _build_fallback_result(
            source_audio_path=source_audio_path,
            metadata=disabled_metadata,
            tags=tuple(),
            fallback_reason="trim_disabled",
        )

    detection = detect_active_speech_span(
        source_audio_path,
        sample_rate=sample_rate,
        top_db=top_db,
        frame_length=frame_length,
        hop_length=hop_length,
        pad_sec=pad_sec,
    )

    if detection.used_fallback:
        return _build_fallback_result(
            source_audio_path=source_audio_path,
            metadata=detection.metadata,
            tags=detection.tags,
        )

    trimmed_duration_sec = float(detection.metadata.get("trimmed_duration_sec", 0.0))
    if trimmed_duration_sec < max(float(min_duration_sec), 0.0):
        return _build_fallback_result(
            source_audio_path=source_audio_path,
            metadata=detection.metadata,
            tags=detection.tags,
            fallback_reason="trimmed_too_short",
        )

    if detection.start_sample <= 0 and detection.end_sample >= detection.total_samples:
        return _build_fallback_result(
            source_audio_path=source_audio_path,
            metadata=detection.metadata,
            tags=detection.tags,
            fallback_reason="no_effective_trim",
        )

    trimmed_waveform = detection.waveform[detection.start_sample : detection.end_sample]
    if trimmed_waveform.size == 0:
        return _build_fallback_result(
            source_audio_path=source_audio_path,
            metadata=detection.metadata,
            tags=detection.tags,
            fallback_reason="empty_trimmed_waveform",
        )

    target_cache_root = Path(cache_dir) if cache_dir is not None else source_audio_path.parent
    target_directory = target_cache_root / TRIMMED_AUDIO_SUBDIR
    target_directory.mkdir(parents=True, exist_ok=True)

    trimmed_path = target_directory / f"{source_audio_path.stem}.trimmed.{uuid.uuid4().hex}.wav"
    try:
        sf.write(
            str(trimmed_path),
            trimmed_waveform.astype(np.float32),
            detection.sample_rate,
        )
    except Exception as exc:
        logger.warning("Failed writing trimmed audio file: %s", exc)
        return _build_fallback_result(
            source_audio_path=source_audio_path,
            metadata=detection.metadata,
            tags=detection.tags,
            fallback_reason=f"trim_write_error:{type(exc).__name__}",
        )

    return TrimmedAudioResult(
        audio_path=str(trimmed_path),
        metadata=detection.metadata,
        tags=detection.tags,
        should_cleanup=True,
    )
