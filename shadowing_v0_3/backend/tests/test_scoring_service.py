from __future__ import annotations

from app.services.audio_embedding_service import ImitationMetrics
from app.services.feature_service import ContentMetrics, ProsodyMetrics
from app.services.scoring_service import (
    fuse_overall_score,
    score_content_branch,
    score_imitation_branch,
    score_prosody_branch,
)


def test_score_content_branch_clamps_into_range() -> None:
    metrics = ContentMetrics(
        normalized_similarity=0.92,
        token_recall=0.88,
        token_precision=0.90,
        token_f1=0.89,
        approx_wer=0.10,
    )
    score = score_content_branch(metrics)
    assert 0 <= score <= 100
    assert score > 80


def test_score_imitation_branch_uses_fallback_when_unavailable() -> None:
    metrics = ImitationMetrics(
        enabled=True,
        available=False,
        model_name="microsoft/wavlm-base-plus",
        fallback_reason="missing_reference_audio",
        global_cosine=0.0,
        chunk_cosine_mean=0.0,
        chunk_cosine_min=0.0,
        chunk_count=0,
    )
    score, available = score_imitation_branch(metrics, fallback_score=73)
    assert score == 73
    assert available is False


def test_score_prosody_branch_returns_fallback_when_unavailable() -> None:
    metrics = ProsodyMetrics(
        available=False,
        fallback_reason="missing_reference_audio",
        duration_ratio=1.2,
        pause_ratio=0.30,
        pause_count=3,
        mean_pause_duration=0.18,
        speech_rate=3.1,
        articulation_rate=4.5,
        voiced_ratio=0.55,
        f0_corr=None,
        pause_ratio_ref=None,
        speech_rate_ref=None,
        articulation_rate_ref=None,
        voiced_ratio_ref=None,
        pause_ratio_delta=None,
    )
    scores = score_prosody_branch(metrics)
    assert 0 <= scores.fluency_score <= 100
    assert 0 <= scores.sync_score <= 100
    assert 0 <= scores.prosody_score <= 100
    assert scores.available_for_fusion is False


def test_fuse_overall_score_renormalizes_active_weights() -> None:
    overall_score, effective_weights = fuse_overall_score(
        content_score=80,
        imitation_score=70,
        prosody_score=90,
        weight_content=0.4,
        weight_imitation=0.35,
        weight_prosody=0.25,
        enable_imitation=True,
        enable_prosody=False,
    )
    assert 0 <= overall_score <= 100
    assert "content" in effective_weights
    assert "imitation" in effective_weights
    assert "prosody" not in effective_weights
