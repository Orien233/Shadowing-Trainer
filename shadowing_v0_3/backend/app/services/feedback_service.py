from __future__ import annotations

from typing import Sequence


_TAG_FEEDBACK_SNIPPETS: dict[str, str] = {
    "content_mismatch": "Some key words from the target sentence are still missing or replaced.",
    "weak_imitation": "Overall timbre and pronunciation style are not close enough to the reference.",
    "too_many_pauses": "There are too many pauses, and continuity is affected.",
    "pace_too_fast": "The pace is a little too fast compared with the reference.",
    "pace_too_slow": "The pace is a little too slow compared with the reference.",
    "intonation_flat": "Intonation contour is relatively flat and less expressive.",
    "imitation_unavailable": "Imitation branch is unavailable, so pronunciation similarity is estimated conservatively.",
    "prosody_unavailable": "Prosody branch is unavailable, so rhythm metrics use fallback logic.",
}

_TAG_SUGGESTION_SNIPPETS: dict[str, str] = {
    "content_mismatch": "Do one slower repetition and ensure all content words are spoken.",
    "weak_imitation": "Shadow the same sentence 2-3 times while focusing on mouth shape and stress placement.",
    "too_many_pauses": "Try shorter pauses between phrase groups and keep airflow steady.",
    "pace_too_fast": "Slightly slow down and keep each phrase complete before moving on.",
    "pace_too_slow": "Speed up by a small step while keeping articulation clear.",
    "intonation_flat": "Mimic the pitch rise/fall of the reference sentence, not only the words.",
    "imitation_unavailable": "Install local WavLM dependencies to enable stronger imitation scoring.",
    "prosody_unavailable": "Provide a valid reference clip to enable full rhythm/prosody comparison.",
}


def build_feedback_and_suggestion(
    *,
    tags: Sequence[str],
    completeness_score: int,
    fluency_score: int,
    sync_score: int,
    pronunciation_score: int,
) -> tuple[str, str]:
    """Generate deterministic rule-based feedback text from tags and scores."""
    if not tags:
        feedback = (
            "Good job. Content, rhythm, and imitation are generally aligned with the reference."
        )
        suggestion = (
            "Next round: keep the same completeness and add slightly stronger sentence-level intonation."
        )
        return feedback, suggestion

    sorted_tags = sorted(set(tags))
    feedback_parts = [
        _TAG_FEEDBACK_SNIPPETS[tag]
        for tag in sorted_tags
        if tag in _TAG_FEEDBACK_SNIPPETS
    ]
    suggestion_parts = [
        _TAG_SUGGESTION_SNIPPETS[tag]
        for tag in sorted_tags
        if tag in _TAG_SUGGESTION_SNIPPETS
    ]

    if not feedback_parts:
        feedback_parts.append(
            "There are a few unstable points in this take across content and rhythm."
        )

    if not suggestion_parts:
        suggestion_parts.append(
            "Repeat the sentence at 0.9x speed first, then return to normal speed."
        )

    score_summary = (
        f"Current scores - content: {completeness_score}, imitation: {pronunciation_score}, "
        f"fluency: {fluency_score}, sync: {sync_score}."
    )
    feedback = " ".join(feedback_parts + [score_summary])
    suggestion = " ".join(suggestion_parts[:2])
    return feedback, suggestion
