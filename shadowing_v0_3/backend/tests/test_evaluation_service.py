from __future__ import annotations

import json

from app.services.audio_embedding_service import ImitationMetrics
from app.services.evaluation_service import evaluate_recording
from app.services.feature_service import ContentMetrics, ProsodyMetrics


def test_evaluate_recording_end_to_end_with_mocked_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.evaluation_service.transcribe_text",
        lambda _path: "hello world",
    )
    monkeypatch.setattr(
        "app.services.evaluation_service._safe_get_duration",
        lambda _path: 2.5,
    )
    monkeypatch.setattr(
        "app.services.evaluation_service.extract_content_metrics",
        lambda _ref, _hyp: ContentMetrics(
            normalized_similarity=0.9,
            token_recall=0.95,
            token_precision=0.9,
            token_f1=0.92,
            approx_wer=0.05,
        ),
    )
    monkeypatch.setattr(
        "app.services.evaluation_service.compute_imitation_metrics",
        lambda **_kwargs: ImitationMetrics(
            enabled=True,
            available=True,
            model_name="microsoft/wavlm-base-plus",
            fallback_reason=None,
            global_cosine=0.82,
            chunk_cosine_mean=0.78,
            chunk_cosine_min=0.70,
            chunk_count=4,
        ),
    )
    monkeypatch.setattr(
        "app.services.evaluation_service.extract_prosody_rhythm_metrics",
        lambda **_kwargs: ProsodyMetrics(
            available=True,
            fallback_reason=None,
            duration_ratio=1.03,
            pause_ratio=0.15,
            pause_count=1,
            mean_pause_duration=0.10,
            speech_rate=3.4,
            articulation_rate=4.2,
            voiced_ratio=0.62,
            f0_corr=0.48,
            pause_ratio_ref=0.14,
            speech_rate_ref=3.3,
            articulation_rate_ref=4.0,
            voiced_ratio_ref=0.60,
            pause_ratio_delta=0.01,
        ),
    )

    result = evaluate_recording(
        reference_text="hello world",
        reference_duration=2.4,
        recording_path="dummy.wav",
        reference_audio_path="ref.wav",
    )

    assert 0 <= result["completeness_score"] <= 100
    assert 0 <= result["fluency_score"] <= 100
    assert 0 <= result["sync_score"] <= 100
    assert 0 <= result["pronunciation_score"] <= 100
    assert 0 <= result["overall_score"] <= 100
    assert result["asr_text"] == "hello world"

    raw_metrics = json.loads(result["raw_metrics"])
    assert raw_metrics["version"] == "multi_branch_v1"
    assert "content" in raw_metrics
    assert "imitation" in raw_metrics
    assert "prosody" in raw_metrics
    assert "scores" in raw_metrics
