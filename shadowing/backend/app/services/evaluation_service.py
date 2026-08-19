from __future__ import annotations

import json
import logging

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
from app.services.asr_router import RECORDING_EVALUATION, transcribe_text_for_scene
from app.services.vad_service import TrimmedAudioResult, create_trimmed_audio
from app.services.word_alignment_service import align_word_tokens


EVALUATION_PIPELINE_VERSION = "multi_branch_v1"
logger = logging.getLogger(__name__)


def _safe_get_duration(audio_path: str) -> float:
    try:
        return float(get_audio_duration(Path(audio_path)))
    except Exception:
        return 0.0


def _resolve_reference_audio_path(reference_audio_path: str | None) -> str | None:
    if not reference_audio_path:
        return None
    if not Path(reference_audio_path).exists():
        return None
    return reference_audio_path


def _merge_tags(*tag_groups: list[str] | tuple[str, ...]) -> list[str]:
    merged: list[str] = []
    for group in tag_groups:
        for tag in group:
            if tag and tag not in merged:
                merged.append(tag)
    return merged


def _cleanup_trimmed_audio(trim_result: TrimmedAudioResult) -> None:
    if not trim_result.should_cleanup:
        return

    trimmed_audio_path = Path(trim_result.audio_path)
    try:
        trimmed_audio_path.unlink(missing_ok=True)
    except Exception:
        logger.warning("Failed deleting temporary trimmed audio: %s", trimmed_audio_path)


def evaluate_recording(
    reference_text: str,
    reference_duration: float,
    recording_path: str,
    reference_audio_path: str | None = None,
    content_language: str | None = None,
) -> dict[str, Any]:
    """Run the local multi-branch evaluator and return legacy-compatible fields."""
    trim_result = create_trimmed_audio(
        recording_path,
        enabled=settings.enable_trim_silence,
        sample_rate=settings.trim_sample_rate,
        top_db=settings.trim_top_db,
        frame_length=settings.trim_frame_length,
        hop_length=settings.trim_hop_length,
        pad_sec=settings.trim_pad_sec,
        min_duration_sec=settings.trim_min_duration_sec,
        cache_dir=settings.cache_dir,
    )
    evaluation_audio_path = trim_result.audio_path

    try:
        asr_text = transcribe_text_for_scene(
            RECORDING_EVALUATION,
            evaluation_audio_path,
            language=content_language,
        )
        duration = _safe_get_duration(evaluation_audio_path)
        safe_reference_duration = max(float(reference_duration), 0.1)
        resolved_reference_audio_path = _resolve_reference_audio_path(reference_audio_path)

        content_metrics = extract_content_metrics(
            reference_text,
            asr_text,
            content_language=content_language,
        )
        word_alignment = align_word_tokens(
            reference_text,
            asr_text,
            content_language=content_language,
        )
        content_score = score_content_branch(content_metrics)

        imitation_metrics = compute_imitation_metrics(
            reference_audio_path=resolved_reference_audio_path,
            learner_audio_path=evaluation_audio_path,
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
            learner_audio_path=evaluation_audio_path,
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

        base_tags = generate_diagnostic_tags(
            content_score=content_score,
            imitation_score=imitation_score,
            prosody_scores=prosody_scores,
            prosody_metrics=prosody_metrics,
            imitation_available=imitation_available_for_fusion,
        )
        tags = _merge_tags(list(trim_result.tags), base_tags)
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
            # These fields are top-level by design: stored raw metrics can be
            # interpreted without assuming every alignment is English word
            # accuracy. The nested copy remains useful to alignment consumers.
            "language": word_alignment["language"],
            "alignment_mode": word_alignment["alignment_mode"],
            "support_level": word_alignment["support_level"],
            "content": content_metrics.to_dict(),
            "imitation": imitation_metrics.to_dict(),
            "prosody": prosody_metrics.to_dict(),
            "scores": score_snapshot,
            "vad": trim_result.metadata,
            "tags": tags,
            "asr_text": asr_text,
            "word_alignment": word_alignment,
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
    finally:
        _cleanup_trimmed_audio(trim_result)
