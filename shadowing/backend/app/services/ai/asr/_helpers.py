"""Normalization helpers for synchronous audio transcription responses."""

from __future__ import annotations

from typing import Any

from app.services.ai.audio_types import ASRSegment, ASRWord
from app.services.ai.audio_utils import as_list, number


def word_from_mapping(item: Any, *, text_keys: tuple[str, ...] = ("word", "text")) -> ASRWord | None:
    if not isinstance(item, dict):
        return None
    text = next((item.get(key) for key in text_keys if item.get(key) is not None), "")
    text = str(text).strip()
    if not text:
        return None
    start = _seconds(item, "start")
    end = _seconds(item, "end")
    if end is None:
        duration = _seconds(item, "duration")
        end = start + duration if start is not None and duration is not None else None
    return ASRWord(text=text, start=start, end=end)


def openai_verbose_result(payload: dict[str, Any], *, include_words: bool) -> tuple[str, list[ASRSegment]]:
    """Normalize OpenAI's verbose-json shape without assuming all keys exist."""
    raw_words = as_list(payload.get("words"))
    words = [word for item in raw_words if (word := word_from_mapping(item))]
    segments: list[ASRSegment] = []
    for raw_segment in as_list(payload.get("segments")):
        if not isinstance(raw_segment, dict):
            continue
        start = number(raw_segment.get("start"))
        end = number(raw_segment.get("end"), start)
        segment_words = [
            word
            for word in words
            if word.start is not None
            and word.end is not None
            and word.start >= start
            and word.end <= end
        ] if include_words else []
        text = str(raw_segment.get("text", "")).strip()
        if text or segment_words:
            segments.append(ASRSegment(text=text, start=start, end=end, words=segment_words))
    text = str(payload.get("text", "")).strip()
    if not segments and words:
        # Some OpenAI-compatible endpoints honour word granularity but omit
        # segment granularity.  Preserve a usable timeline rather than
        # returning the legacy ASR default of (0, 0), which would collapse an
        # entire uploaded material into a near-zero-duration clip downstream.
        starts = [word.start for word in words if word.start is not None]
        ends = [word.end for word in words if word.end is not None]
        start = min(starts, default=0.0)
        end = max(ends, default=number(payload.get("duration"), start))
        end = max(end, start)
        fallback_text = text or " ".join(word.text for word in words).strip()
        segments = [
            ASRSegment(
                text=fallback_text,
                start=start,
                end=end,
                words=words if include_words else [],
            )
        ]
    elif not segments and text:
        duration = max(number(payload.get("duration"), 0.0), 0.0)
        segments = [ASRSegment(text=text, start=0.0, end=duration)]
    return text or " ".join(segment.text for segment in segments).strip(), segments


def _seconds(item: dict[str, Any], prefix: str) -> float | None:
    """Read an optional timing value expressed in seconds."""
    direct = item.get(prefix)
    return number(direct) if direct is not None else None
