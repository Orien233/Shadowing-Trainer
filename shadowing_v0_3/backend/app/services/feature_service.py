from __future__ import annotations

import logging
import re

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import librosa
import numpy as np

from app.utils.text_utils import normalize_text, similarity


logger = logging.getLogger(__name__)
_EPSILON = 1e-8
_CJK_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True)
class ContentMetrics:
    """Text content metrics computed without word-level alignment."""

    normalized_similarity: float
    token_recall: float
    token_precision: float
    token_f1: float
    approx_wer: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProsodyMetrics:
    """Prosody and rhythm metrics extracted from learner/reference audio."""

    available: bool
    fallback_reason: str | None
    duration_ratio: float
    pause_ratio: float
    pause_count: int
    mean_pause_duration: float
    speech_rate: float
    articulation_rate: float
    voiced_ratio: float
    f0_corr: float | None
    pause_ratio_ref: float | None
    speech_rate_ref: float | None
    articulation_rate_ref: float | None
    voiced_ratio_ref: float | None
    pause_ratio_delta: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _PauseStats:
    pause_ratio: float
    pause_count: int
    mean_pause_duration: float
    active_duration: float


def _contains_cjk_chars(text: str) -> bool:
    return bool(_CJK_CHAR_PATTERN.search(text))


def tokenize_for_content_metrics(text: str) -> list[str]:
    """Tokenize text for rough content scoring.

    The tokenizer is intentionally lightweight. It uses whitespace tokens first,
    and falls back to character tokens for CJK text with no spaces.
    """
    normalized = normalize_text(text)
    if not normalized:
        return []

    whitespace_tokens = normalized.split()
    if len(whitespace_tokens) > 1:
        return whitespace_tokens

    if _contains_cjk_chars(normalized):
        return [char for char in normalized if not char.isspace()]

    return whitespace_tokens


def _safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator <= _EPSILON:
        return default
    return float(numerator / denominator)


def _clamp_unit(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _token_overlap_count(reference_tokens: Sequence[str], hypothesis_tokens: Sequence[str]) -> int:
    reference_counts = Counter(reference_tokens)
    hypothesis_counts = Counter(hypothesis_tokens)
    return int(
        sum(
            min(reference_counts[token], hypothesis_counts[token])
            for token in reference_counts
        )
    )


def _approximate_wer(reference_tokens: Sequence[str], hypothesis_tokens: Sequence[str]) -> float:
    if not reference_tokens:
        return 1.0 if hypothesis_tokens else 0.0

    rows = len(reference_tokens) + 1
    cols = len(hypothesis_tokens) + 1
    distance = [[0] * cols for _ in range(rows)]

    for row in range(rows):
        distance[row][0] = row
    for col in range(cols):
        distance[0][col] = col

    for row in range(1, rows):
        for col in range(1, cols):
            substitution_cost = 0 if reference_tokens[row - 1] == hypothesis_tokens[col - 1] else 1
            distance[row][col] = min(
                distance[row - 1][col] + 1,
                distance[row][col - 1] + 1,
                distance[row - 1][col - 1] + substitution_cost,
            )

    return _clamp_unit(distance[-1][-1] / max(len(reference_tokens), 1))


def extract_content_metrics(reference_text: str, hypothesis_text: str) -> ContentMetrics:
    """Extract sentence-level content metrics without forced alignment."""
    reference_tokens = tokenize_for_content_metrics(reference_text)
    hypothesis_tokens = tokenize_for_content_metrics(hypothesis_text)
    overlap = _token_overlap_count(reference_tokens, hypothesis_tokens)

    recall = _safe_ratio(overlap, float(len(reference_tokens)))
    precision = _safe_ratio(overlap, float(len(hypothesis_tokens)))
    f1 = _safe_ratio(2.0 * precision * recall, precision + recall)
    approx_wer = _approximate_wer(reference_tokens, hypothesis_tokens)
    normalized_similarity = _clamp_unit(similarity(reference_text, hypothesis_text))

    return ContentMetrics(
        normalized_similarity=normalized_similarity,
        token_recall=_clamp_unit(recall),
        token_precision=_clamp_unit(precision),
        token_f1=_clamp_unit(f1),
        approx_wer=approx_wer,
    )


def _load_audio_mono(audio_path: str | Path, sample_rate: int) -> tuple[np.ndarray, int]:
    waveform, loaded_sr = librosa.load(str(audio_path), sr=sample_rate, mono=True)
    if waveform.size == 0:
        raise ValueError("Audio is empty.")
    return np.asarray(waveform, dtype=np.float32), int(loaded_sr)


def _compute_pause_stats(
    waveform: np.ndarray,
    sample_rate: int,
    *,
    top_db: float = 25.0,
    min_pause_seconds: float = 0.08,
) -> _PauseStats:
    total_duration = max(len(waveform) / float(sample_rate), _EPSILON)
    non_silent = librosa.effects.split(waveform, top_db=top_db)

    if len(non_silent) == 0:
        return _PauseStats(
            pause_ratio=1.0,
            pause_count=1,
            mean_pause_duration=total_duration,
            active_duration=0.0,
        )

    active_duration = float(
        sum((end - start) for start, end in non_silent) / float(sample_rate)
    )
    active_duration = max(active_duration, 0.0)
    pause_ratio = _clamp_unit((total_duration - active_duration) / total_duration)

    pauses: list[float] = []
    cursor = 0.0
    for start_sample, end_sample in non_silent:
        start_time = float(start_sample) / float(sample_rate)
        if start_time > cursor:
            pauses.append(start_time - cursor)
        cursor = float(end_sample) / float(sample_rate)

    if cursor < total_duration:
        pauses.append(total_duration - cursor)

    valid_pauses = [pause for pause in pauses if pause >= min_pause_seconds]
    pause_count = len(valid_pauses)
    mean_pause_duration = float(np.mean(valid_pauses)) if valid_pauses else 0.0

    return _PauseStats(
        pause_ratio=pause_ratio,
        pause_count=pause_count,
        mean_pause_duration=mean_pause_duration,
        active_duration=active_duration,
    )


def _compute_onset_rates(
    waveform: np.ndarray,
    sample_rate: int,
    *,
    total_duration: float,
    active_duration: float,
) -> tuple[float, float]:
    onset_envelope = librosa.onset.onset_strength(y=waveform, sr=sample_rate)
    onsets = librosa.onset.onset_detect(
        onset_envelope=onset_envelope,
        sr=sample_rate,
        units="time",
        backtrack=False,
    )
    event_count = float(len(onsets))
    speech_rate = _safe_ratio(event_count, max(total_duration, _EPSILON))
    articulation_rate = _safe_ratio(event_count, max(active_duration, _EPSILON))
    return speech_rate, articulation_rate


def _extract_f0_and_voiced_ratio(
    waveform: np.ndarray,
    sample_rate: int,
) -> tuple[np.ndarray, float]:
    try:
        f0, voiced_flag, _ = librosa.pyin(
            waveform,
            sr=sample_rate,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
        )
    except Exception:
        return np.asarray([], dtype=np.float32), 0.0

    if f0 is None:
        return np.asarray([], dtype=np.float32), 0.0

    voiced_f0 = np.asarray(f0[~np.isnan(f0)], dtype=np.float32)
    if voiced_flag is None:
        voiced_ratio = _safe_ratio(float(len(voiced_f0)), float(len(f0)))
    else:
        voiced_ratio = float(np.mean(np.asarray(voiced_flag, dtype=np.float32)))
    return voiced_f0, _clamp_unit(voiced_ratio)


def _resample_array(values: np.ndarray, target_length: int) -> np.ndarray:
    if len(values) == target_length:
        return values
    if len(values) <= 1 or target_length <= 1:
        return np.asarray([], dtype=np.float32)

    source_positions = np.linspace(0.0, 1.0, num=len(values))
    target_positions = np.linspace(0.0, 1.0, num=target_length)
    return np.interp(target_positions, source_positions, values).astype(np.float32)


def _compute_f0_correlation(reference_f0: np.ndarray, learner_f0: np.ndarray) -> float | None:
    if len(reference_f0) < 3 or len(learner_f0) < 3:
        return None

    target_length = min(len(reference_f0), len(learner_f0), 256)
    ref = _resample_array(reference_f0, target_length)
    learner = _resample_array(learner_f0, target_length)
    if len(ref) == 0 or len(learner) == 0:
        return None

    ref_log = np.log(np.maximum(ref, _EPSILON))
    learner_log = np.log(np.maximum(learner, _EPSILON))

    ref_std = float(np.std(ref_log))
    learner_std = float(np.std(learner_log))
    if ref_std <= _EPSILON or learner_std <= _EPSILON:
        return 0.0

    corr = float(np.corrcoef(ref_log, learner_log)[0, 1])
    if np.isnan(corr):
        return None
    return float(max(-1.0, min(1.0, corr)))


def _safe_reference_duration(
    reference_duration: float | None,
    reference_waveform: np.ndarray | None,
    sample_rate: int,
) -> float:
    if reference_duration is not None and reference_duration > 0:
        return float(reference_duration)
    if reference_waveform is not None:
        return max(len(reference_waveform) / float(sample_rate), _EPSILON)
    return 1.0


def extract_prosody_rhythm_metrics(
    reference_audio_path: str | None,
    learner_audio_path: str,
    *,
    reference_duration: float | None = None,
    sample_rate: int = 16000,
    backend: str = "librosa_pyin",
    enabled: bool = True,
) -> ProsodyMetrics:
    """Extract rhythm/intonation metrics with robust fallback behavior."""
    if not enabled:
        return ProsodyMetrics(
            available=False,
            fallback_reason="prosody_disabled",
            duration_ratio=1.0,
            pause_ratio=0.0,
            pause_count=0,
            mean_pause_duration=0.0,
            speech_rate=0.0,
            articulation_rate=0.0,
            voiced_ratio=0.0,
            f0_corr=None,
            pause_ratio_ref=None,
            speech_rate_ref=None,
            articulation_rate_ref=None,
            voiced_ratio_ref=None,
            pause_ratio_delta=None,
        )

    normalized_backend = backend.strip().lower()
    if normalized_backend != "librosa_pyin":
        return ProsodyMetrics(
            available=False,
            fallback_reason=f"unsupported_prosody_backend:{normalized_backend}",
            duration_ratio=1.0,
            pause_ratio=0.0,
            pause_count=0,
            mean_pause_duration=0.0,
            speech_rate=0.0,
            articulation_rate=0.0,
            voiced_ratio=0.0,
            f0_corr=None,
            pause_ratio_ref=None,
            speech_rate_ref=None,
            articulation_rate_ref=None,
            voiced_ratio_ref=None,
            pause_ratio_delta=None,
        )

    try:
        learner_waveform, learner_sr = _load_audio_mono(learner_audio_path, sample_rate)
    except Exception as exc:
        logger.warning("Failed loading learner audio for prosody metrics: %s", exc)
        return ProsodyMetrics(
            available=False,
            fallback_reason=f"learner_audio_error:{type(exc).__name__}",
            duration_ratio=1.0,
            pause_ratio=1.0,
            pause_count=1,
            mean_pause_duration=0.0,
            speech_rate=0.0,
            articulation_rate=0.0,
            voiced_ratio=0.0,
            f0_corr=None,
            pause_ratio_ref=None,
            speech_rate_ref=None,
            articulation_rate_ref=None,
            voiced_ratio_ref=None,
            pause_ratio_delta=None,
        )

    learner_duration = max(len(learner_waveform) / float(learner_sr), _EPSILON)
    learner_pause = _compute_pause_stats(learner_waveform, learner_sr)
    learner_speech_rate, learner_articulation_rate = _compute_onset_rates(
        learner_waveform,
        learner_sr,
        total_duration=learner_duration,
        active_duration=learner_pause.active_duration,
    )
    learner_f0, learner_voiced_ratio = _extract_f0_and_voiced_ratio(learner_waveform, learner_sr)

    reference_waveform: np.ndarray | None = None
    reference_sr = sample_rate
    reference_available = False
    reference_pause_ratio: float | None = None
    reference_speech_rate: float | None = None
    reference_articulation_rate: float | None = None
    reference_voiced_ratio: float | None = None
    reference_f0 = np.asarray([], dtype=np.float32)
    fallback_reason: str | None = None

    if reference_audio_path:
        try:
            reference_waveform, reference_sr = _load_audio_mono(reference_audio_path, sample_rate)
            reference_duration_for_rates = max(
                len(reference_waveform) / float(reference_sr),
                _EPSILON,
            )
            reference_pause = _compute_pause_stats(reference_waveform, reference_sr)
            reference_speech_rate, reference_articulation_rate = _compute_onset_rates(
                reference_waveform,
                reference_sr,
                total_duration=reference_duration_for_rates,
                active_duration=reference_pause.active_duration,
            )
            reference_f0, reference_voiced_ratio = _extract_f0_and_voiced_ratio(
                reference_waveform,
                reference_sr,
            )
            reference_pause_ratio = reference_pause.pause_ratio
            reference_available = True
        except Exception as exc:
            logger.warning("Failed loading reference audio for prosody metrics: %s", exc)
            fallback_reason = f"reference_audio_error:{type(exc).__name__}"
    else:
        fallback_reason = "missing_reference_audio"

    effective_reference_duration = _safe_reference_duration(
        reference_duration=reference_duration,
        reference_waveform=reference_waveform,
        sample_rate=reference_sr,
    )
    duration_ratio = learner_duration / max(effective_reference_duration, _EPSILON)
    pause_ratio_delta = (
        abs(learner_pause.pause_ratio - reference_pause_ratio)
        if reference_pause_ratio is not None
        else None
    )

    f0_corr = _compute_f0_correlation(reference_f0, learner_f0) if reference_available else None
    available = reference_available

    return ProsodyMetrics(
        available=available,
        fallback_reason=fallback_reason,
        duration_ratio=float(duration_ratio),
        pause_ratio=learner_pause.pause_ratio,
        pause_count=learner_pause.pause_count,
        mean_pause_duration=learner_pause.mean_pause_duration,
        speech_rate=float(learner_speech_rate),
        articulation_rate=float(learner_articulation_rate),
        voiced_ratio=learner_voiced_ratio,
        f0_corr=f0_corr,
        pause_ratio_ref=reference_pause_ratio,
        speech_rate_ref=reference_speech_rate,
        articulation_rate_ref=reference_articulation_rate,
        voiced_ratio_ref=reference_voiced_ratio,
        pause_ratio_delta=pause_ratio_delta,
    )
