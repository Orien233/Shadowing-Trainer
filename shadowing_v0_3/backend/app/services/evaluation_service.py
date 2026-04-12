from __future__ import annotations

import json

from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.audio_embedding_service import compute_imitation_metrics
from app.services.feature_service import extract_content_metrics, extract_prosody_rhythm_metrics
from app.services.feedback_service import build_feedback_and_suggestion
from app.services.media_service import get_audio_duration
from app.services.scoring_service import (
    ProsodyBranchScores,
    build_branch_scores_snapshot,
    fuse_overall_score,
    generate_diagnostic_tags,
    score_content_branch,
    score_imitation_branch,
    score_prosody_branch,
)
from app.services.transcription_service import transcribe_text


EVALUATION_PIPELINE_VERSION = "multi_branch_v1"


def _safe_get_duration(audio_path: str) -> float:
    try:
        return float(get_audio_duration(Path(audio_path)))
    except Exception:
        return 0.0


def _legacy_pause_ratio_from_prosody_metrics(recording_path: str) -> float:
    metrics = extract_prosody_rhythm_metrics(
        reference_audio_path=None,
        learner_audio_path=recording_path,
        reference_duration=None,
        sample_rate=settings.eval_sample_rate,
        backend=settings.prosody_backend,
        enabled=True,
    )
    return float(metrics.pause_ratio)


def estimate_pause_ratio(audio_path: str) -> float:
    """Backward-compatible helper kept for legacy callers."""
    return _legacy_pause_ratio_from_prosody_metrics(audio_path)


def _legacy_feedback_tags(
    *,
    completeness_score: int,
    fluency_score: int,
    sync_score: int,
    pronunciation_score: int,
) -> list[str]:
    tags: list[str] = []
    if completeness_score < 70:
        tags.append("content_mismatch")
    if fluency_score < 70:
        tags.append("too_many_pauses")
    if sync_score < 70:
        tags.append("pace_too_slow")
    if pronunciation_score < 70:
        tags.append("weak_imitation")
    return tags


def build_feedback(
    completeness_score: int,
    fluency_score: int,
    sync_score: int,
    pronunciation_score: int,
) -> tuple[str, str]:
    """Backward-compatible wrapper for deterministic feedback generation."""
    tags = _legacy_feedback_tags(
        completeness_score=completeness_score,
        fluency_score=fluency_score,
        sync_score=sync_score,
        pronunciation_score=pronunciation_score,
    )
    return build_feedback_and_suggestion(
        tags=tags,
        completeness_score=completeness_score,
        fluency_score=fluency_score,
        sync_score=sync_score,
        pronunciation_score=pronunciation_score,
    )


def _resolve_reference_audio_path(reference_audio_path: str | None) -> str | None:
    if not reference_audio_path:
        return None
    if not Path(reference_audio_path).exists():
        return None
    return reference_audio_path


def evaluate_recording(
    reference_text: str,
    reference_duration: float,
    recording_path: str,
    reference_audio_path: str | None = None,
) -> dict[str, Any]:
    """Run the local multi-branch evaluator and return legacy-compatible fields."""
    asr_text = transcribe_text(recording_path)
    duration = _safe_get_duration(recording_path)
    safe_reference_duration = max(float(reference_duration), 0.1)
    resolved_reference_audio_path = _resolve_reference_audio_path(reference_audio_path)

    content_metrics = extract_content_metrics(reference_text, asr_text)
    content_score = score_content_branch(content_metrics)

    imitation_metrics = compute_imitation_metrics(
        reference_audio_path=resolved_reference_audio_path,
        learner_audio_path=recording_path,
        enabled=settings.enable_wavlm_score,
        model_name=settings.wavlm_model_name,
        device=settings.wavlm_device,
        sample_rate=settings.eval_sample_rate,
        chunk_count=settings.wavlm_chunk_count,
        min_chunk_seconds=settings.wavlm_min_chunk_seconds,
    )
    imitation_score, imitation_available_for_fusion = score_imitation_branch(
        imitation_metrics,
        fallback_score=content_score,
    )

    prosody_metrics = extract_prosody_rhythm_metrics(
        reference_audio_path=resolved_reference_audio_path,
        learner_audio_path=recording_path,
        reference_duration=safe_reference_duration,
        sample_rate=settings.eval_sample_rate,
        backend=settings.prosody_backend,
        enabled=settings.enable_prosody_score,
    )
    prosody_scores: ProsodyBranchScores = score_prosody_branch(prosody_metrics)

    overall_score, effective_weights = fuse_overall_score(
        content_score=content_score,
        imitation_score=imitation_score,
        prosody_score=prosody_scores.prosody_score,
        weight_content=settings.eval_weight_content,
        weight_imitation=settings.eval_weight_imitation,
        weight_prosody=settings.eval_weight_prosody,
        enable_imitation=imitation_available_for_fusion,
        enable_prosody=prosody_scores.available_for_fusion,
    )

    tags = generate_diagnostic_tags(
        content_score=content_score,
        imitation_score=imitation_score,
        prosody_scores=prosody_scores,
        prosody_metrics=prosody_metrics,
        imitation_available=imitation_available_for_fusion,
    )
    feedback, suggestion = build_feedback_and_suggestion(
        tags=tags,
        completeness_score=content_score,
        fluency_score=prosody_scores.fluency_score,
        sync_score=prosody_scores.sync_score,
        pronunciation_score=imitation_score,
    )

    score_snapshot = build_branch_scores_snapshot(
        content_score=content_score,
        imitation_score=imitation_score,
        prosody_scores=prosody_scores,
        overall_score=overall_score,
        effective_weights=effective_weights,
        imitation_available_for_fusion=imitation_available_for_fusion,
    )

    raw_metrics_payload = {
        "version": EVALUATION_PIPELINE_VERSION,
        "content": content_metrics.to_dict(),
        "imitation": imitation_metrics.to_dict(),
        "prosody": prosody_metrics.to_dict(),
        "scores": score_snapshot,
        "tags": tags,
        "asr_text": asr_text,
        "duration": duration,
        "legacy": {
            "recall": content_metrics.token_recall,
            "similarity": content_metrics.normalized_similarity,
            "pause_ratio": prosody_metrics.pause_ratio,
            "duration_ratio": prosody_metrics.duration_ratio,
            "asr_text": asr_text,
        },
    }

    return {
        "asr_text": asr_text,
        "duration": duration,
        "completeness_score": content_score,
        "fluency_score": prosody_scores.fluency_score,
        "sync_score": prosody_scores.sync_score,
        "pronunciation_score": imitation_score,
        "overall_score": overall_score,
        "feedback": feedback,
        "suggestion": suggestion,
        "raw_metrics": json.dumps(raw_metrics_payload, ensure_ascii=False),
    }
