from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.audio_embedding_service import ImitationMetrics
from app.services.feature_service import ContentMetrics, ProsodyMetrics
from app.utils.text_utils import clamp_score


@dataclass(frozen=True)
class NormalizationConfig:
    """Centralized constants for branch score normalization."""

    content_similarity_weight: float = 0.45
    content_recall_weight: float = 0.30
    content_precision_weight: float = 0.20
    content_f1_weight: float = 0.05
    content_wer_penalty_weight: float = 0.20
    imitation_global_weight: float = 0.65
    imitation_chunk_mean_weight: float = 0.25
    imitation_chunk_min_weight: float = 0.10
    prosody_pause_weight: float = 0.30
    prosody_rate_weight: float = 0.25
    prosody_articulation_weight: float = 0.20
    prosody_voiced_weight: float = 0.25
    sync_duration_weight: float = 0.45
    sync_pause_weight: float = 0.35
    sync_f0_weight: float = 0.20
    ratio_tolerance: float = 0.35
    pause_tolerance: float = 0.20


@dataclass(frozen=True)
class ProsodyBranchScores:
    """Prosody branch score outputs and compatibility mapping fields."""

    prosody_score: int
    fluency_score: int
    sync_score: int
    available_for_fusion: bool


def _clamp_unit(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _ratio_similarity(ratio: float, tolerance: float) -> float:
    if ratio <= 0:
        return 0.0
    return _clamp_unit(1.0 - abs(1.0 - ratio) / max(tolerance, 1e-6))


def _difference_similarity(delta: float, tolerance: float) -> float:
    return _clamp_unit(1.0 - abs(delta) / max(tolerance, 1e-6))


def score_content_branch(
    metrics: ContentMetrics,
    *,
    config: NormalizationConfig | None = None,
) -> int:
    """Convert text metrics into a normalized [0, 100] content score."""
    cfg = config or NormalizationConfig()
    base_score = (
        metrics.normalized_similarity * cfg.content_similarity_weight
        + metrics.token_recall * cfg.content_recall_weight
        + metrics.token_precision * cfg.content_precision_weight
        + metrics.token_f1 * cfg.content_f1_weight
    )
    wer_penalty = 1.0 - cfg.content_wer_penalty_weight * _clamp_unit(metrics.approx_wer)
    return clamp_score(base_score * wer_penalty * 100.0)


def score_imitation_branch(
    metrics: ImitationMetrics,
    *,
    fallback_score: int,
    config: NormalizationConfig | None = None,
) -> tuple[int, bool]:
    """Convert WavLM imitation metrics into a normalized [0, 100] score."""
    if not metrics.available:
        return clamp_score(float(fallback_score)), False

    cfg = config or NormalizationConfig()
    score_value = (
        metrics.global_cosine * cfg.imitation_global_weight
        + metrics.chunk_cosine_mean * cfg.imitation_chunk_mean_weight
        + metrics.chunk_cosine_min * cfg.imitation_chunk_min_weight
    )
    return clamp_score(score_value * 100.0), True


def _legacy_prosody_fallback(prosody_metrics: ProsodyMetrics) -> ProsodyBranchScores:
    fluency_score = clamp_score(100.0 - prosody_metrics.pause_ratio * 120.0)
    sync_score = clamp_score(100.0 - abs(1.0 - prosody_metrics.duration_ratio) * 120.0)
    prosody_score = clamp_score((fluency_score + sync_score) * 0.5)
    return ProsodyBranchScores(
        prosody_score=prosody_score,
        fluency_score=fluency_score,
        sync_score=sync_score,
        available_for_fusion=False,
    )


def score_prosody_branch(
    metrics: ProsodyMetrics,
    *,
    config: NormalizationConfig | None = None,
) -> ProsodyBranchScores:
    """Convert prosody feature metrics into fluency/sync/prosody scores."""
    if not metrics.available:
        return _legacy_prosody_fallback(metrics)

    cfg = config or NormalizationConfig()
    pause_similarity = (
        _difference_similarity(metrics.pause_ratio_delta, cfg.pause_tolerance)
        if metrics.pause_ratio_delta is not None
        else _difference_similarity(metrics.pause_ratio, cfg.pause_tolerance)
    )

    reference_speech_rate = metrics.speech_rate_ref if metrics.speech_rate_ref else None
    if reference_speech_rate is None or reference_speech_rate <= 0:
        rate_similarity = _ratio_similarity(metrics.duration_ratio, cfg.ratio_tolerance)
    else:
        rate_similarity = _ratio_similarity(
            metrics.speech_rate / max(reference_speech_rate, 1e-6),
            cfg.ratio_tolerance,
        )

    reference_articulation_rate = (
        metrics.articulation_rate_ref if metrics.articulation_rate_ref else None
    )
    if reference_articulation_rate is None or reference_articulation_rate <= 0:
        articulation_similarity = _ratio_similarity(metrics.duration_ratio, cfg.ratio_tolerance)
    else:
        articulation_similarity = _ratio_similarity(
            metrics.articulation_rate / max(reference_articulation_rate, 1e-6),
            cfg.ratio_tolerance,
        )

    if metrics.voiced_ratio_ref is None:
        voiced_similarity = _difference_similarity(metrics.voiced_ratio, 0.35)
    else:
        voiced_similarity = _difference_similarity(
            metrics.voiced_ratio - metrics.voiced_ratio_ref,
            0.35,
        )

    fluency_unit_score = (
        pause_similarity * cfg.prosody_pause_weight
        + rate_similarity * cfg.prosody_rate_weight
        + articulation_similarity * cfg.prosody_articulation_weight
        + voiced_similarity * cfg.prosody_voiced_weight
    )
    fluency_score = clamp_score(fluency_unit_score * 100.0)

    duration_similarity = _ratio_similarity(metrics.duration_ratio, cfg.ratio_tolerance)
    f0_similarity = (
        _clamp_unit((metrics.f0_corr + 1.0) * 0.5)
        if metrics.f0_corr is not None
        else 0.5
    )
    sync_unit_score = (
        duration_similarity * cfg.sync_duration_weight
        + pause_similarity * cfg.sync_pause_weight
        + f0_similarity * cfg.sync_f0_weight
    )
    sync_score = clamp_score(sync_unit_score * 100.0)

    prosody_score = clamp_score(fluency_score * 0.55 + sync_score * 0.45)
    return ProsodyBranchScores(
        prosody_score=prosody_score,
        fluency_score=fluency_score,
        sync_score=sync_score,
        available_for_fusion=True,
    )


def fuse_overall_score(
    *,
    content_score: int,
    imitation_score: int,
    prosody_score: int,
    weight_content: float,
    weight_imitation: float,
    weight_prosody: float,
    enable_imitation: bool,
    enable_prosody: bool,
) -> tuple[int, dict[str, float]]:
    """Fuse branch scores with weight re-normalization over active branches."""
    branch_candidates = [
        ("content", max(weight_content, 0.0), float(content_score), True),
        ("imitation", max(weight_imitation, 0.0), float(imitation_score), enable_imitation),
        ("prosody", max(weight_prosody, 0.0), float(prosody_score), enable_prosody),
    ]
    active_branches = [item for item in branch_candidates if item[3]]
    if not active_branches:
        active_branches = [("content", 1.0, float(content_score), True)]

    weight_total = sum(weight for _, weight, _, _ in active_branches)
    if weight_total <= 0:
        normalized = {
            name: (1.0 / len(active_branches))
            for name, _, _, _ in active_branches
        }
    else:
        normalized = {
            name: weight / weight_total
            for name, weight, _, _ in active_branches
        }

    overall_value = sum(
        score_value * normalized[name]
        for name, _, score_value, _ in active_branches
    )
    return clamp_score(overall_value), normalized


def generate_diagnostic_tags(
    *,
    content_score: int,
    imitation_score: int,
    prosody_scores: ProsodyBranchScores,
    prosody_metrics: ProsodyMetrics,
    imitation_available: bool,
) -> list[str]:
    """Generate deterministic diagnostics tags for downstream feedback."""
    tags: list[str] = []
    if content_score < 65:
        tags.append("content_mismatch")

    if imitation_available and imitation_score < 65:
        tags.append("weak_imitation")

    if prosody_metrics.pause_ratio > 0.34 and prosody_metrics.pause_count >= 2:
        tags.append("too_many_pauses")

    reference_speech_rate = prosody_metrics.speech_rate_ref
    if reference_speech_rate and reference_speech_rate > 0:
        rate_ratio = prosody_metrics.speech_rate / max(reference_speech_rate, 1e-6)
        if rate_ratio > 1.25:
            tags.append("pace_too_fast")
        elif rate_ratio < 0.80:
            tags.append("pace_too_slow")
    elif prosody_metrics.duration_ratio > 1.30:
        tags.append("pace_too_slow")
    elif prosody_metrics.duration_ratio < 0.75:
        tags.append("pace_too_fast")

    if prosody_metrics.f0_corr is not None and prosody_metrics.f0_corr < 0.20:
        tags.append("intonation_flat")

    if not imitation_available:
        tags.append("imitation_unavailable")
    if not prosody_scores.available_for_fusion:
        tags.append("prosody_unavailable")

    deduplicated = sorted(set(tags))
    return deduplicated


def build_branch_scores_snapshot(
    *,
    content_score: int,
    imitation_score: int,
    prosody_scores: ProsodyBranchScores,
    overall_score: int,
    effective_weights: dict[str, float],
    imitation_available_for_fusion: bool,
) -> dict[str, Any]:
    """Build a structured score snapshot for raw_metrics payload."""
    return {
        "content_score": content_score,
        "imitation_score": imitation_score,
        "prosody_score": prosody_scores.prosody_score,
        "fluency_score": prosody_scores.fluency_score,
        "sync_score": prosody_scores.sync_score,
        "overall_score": overall_score,
        "effective_weights": effective_weights,
        "imitation_available_for_fusion": imitation_available_for_fusion,
        "prosody_available_for_fusion": prosody_scores.available_for_fusion,
    }
