from __future__ import annotations

from app.services.feature_service import (
    extract_content_metrics,
    extract_prosody_rhythm_metrics,
    tokenize_for_content_metrics,
)


def test_extract_content_metrics_basic() -> None:
    metrics = extract_content_metrics("hello world", "hello brave world")
    assert 0.0 <= metrics.normalized_similarity <= 1.0
    assert metrics.token_recall == 1.0
    assert 0.6 < metrics.token_precision < 0.8
    assert 0.0 <= metrics.token_f1 <= 1.0
    assert 0.0 <= metrics.approx_wer <= 1.0


def test_tokenize_for_content_metrics_cjk_fallback() -> None:
    tokens = tokenize_for_content_metrics("你好世界")
    assert tokens == ["你", "好", "世", "界"]


def test_extract_prosody_rhythm_metrics_fallback_on_missing_audio() -> None:
    metrics = extract_prosody_rhythm_metrics(
        reference_audio_path=None,
        learner_audio_path="missing-file.wav",
        reference_duration=2.0,
        enabled=True,
    )
    assert metrics.available is False
    assert metrics.fallback_reason is not None
    assert metrics.fallback_reason.startswith("learner_audio_error:")
    assert metrics.pause_ratio >= 0.0
