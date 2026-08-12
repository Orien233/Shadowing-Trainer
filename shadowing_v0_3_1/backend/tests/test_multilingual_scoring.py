import json
from types import SimpleNamespace

from app.services import evaluation_service
from app.services.feature_service import tokenize_for_content_metrics
from app.services.scoring_service import ProsodyBranchScores
from app.services.vad_service import TrimmedAudioResult


def test_content_metrics_use_cjk_character_tokens_when_language_is_provided():
    assert tokenize_for_content_metrics(
        "\u4f60\u597d\u4e16\u754c",
        content_language="zh-CN",
    ) == ["\u4f60", "\u597d", "\u4e16", "\u754c"]


def test_evaluation_passes_content_language_to_metrics_and_records_alignment_profile(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        evaluation_service,
        "create_trimmed_audio",
        lambda recording_path, **_kwargs: TrimmedAudioResult(
            audio_path=recording_path,
            metadata={},
            tags=(),
            should_cleanup=False,
        ),
    )
    monkeypatch.setattr(evaluation_service, "transcribe_text_for_scene", lambda *_args, **_kwargs: "\u3053\u3093\u306b\u3061\u306f")
    monkeypatch.setattr(evaluation_service, "_safe_get_duration", lambda _path: 1.0)

    def fake_content_metrics(_reference, _asr, *, content_language=None):
        captured["content_language"] = content_language
        return SimpleNamespace(
            token_recall=1.0,
            normalized_similarity=1.0,
            to_dict=lambda: {"metric": "content"},
        )

    def fake_alignment(_reference, _asr, *, content_language=None):
        captured["alignment_language"] = content_language
        return {
            "language": "ja",
            "alignment_mode": "unicode_character",
            "support_level": "limited",
            "reference_tokens": [],
            "user_tokens": [],
            "summary": {},
        }

    monkeypatch.setattr(evaluation_service, "extract_content_metrics", fake_content_metrics)
    monkeypatch.setattr(evaluation_service, "align_word_tokens", fake_alignment)
    monkeypatch.setattr(evaluation_service, "score_content_branch", lambda _metrics: 80)
    monkeypatch.setattr(
        evaluation_service,
        "compute_imitation_metrics",
        lambda **_kwargs: SimpleNamespace(to_dict=lambda: {"metric": "imitation"}),
    )
    monkeypatch.setattr(evaluation_service, "score_imitation_branch", lambda *_args, **_kwargs: (80, False))
    monkeypatch.setattr(
        evaluation_service,
        "extract_prosody_rhythm_metrics",
        lambda **_kwargs: SimpleNamespace(
            pause_ratio=0.0,
            duration_ratio=1.0,
            to_dict=lambda: {"metric": "prosody"},
        ),
    )
    monkeypatch.setattr(
        evaluation_service,
        "score_prosody_branch",
        lambda _metrics: ProsodyBranchScores(80, 80, 80, False),
    )
    monkeypatch.setattr(evaluation_service, "fuse_overall_score", lambda **_kwargs: (80, {}))
    monkeypatch.setattr(evaluation_service, "generate_diagnostic_tags", lambda **_kwargs: [])
    monkeypatch.setattr(evaluation_service, "build_feedback_and_suggestion", lambda **_kwargs: ("feedback", "suggestion"))
    monkeypatch.setattr(evaluation_service, "build_branch_scores_snapshot", lambda **_kwargs: {})

    result = evaluation_service.evaluate_recording(
        "\u3053\u3093\u306b\u3061\u306f",
        1.0,
        "recording.wav",
        content_language="ja",
    )
    raw_metrics = json.loads(result["raw_metrics"])

    assert captured == {"content_language": "ja", "alignment_language": "ja"}
    assert raw_metrics["language"] == "ja"
    assert raw_metrics["alignment_mode"] == "unicode_character"
    assert raw_metrics["support_level"] == "limited"
