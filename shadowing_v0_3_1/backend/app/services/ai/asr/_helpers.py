"""Normalization helpers for synchronous audio transcription responses."""

from __future__ import annotations

from typing import Any

from app.services.ai.audio_types import ASRSegment, ASRWord
from app.services.ai.audio_utils import as_list, as_mapping, number


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
    if not segments and text:
        segments = [ASRSegment(text=text, words=words if include_words else [])]
    return text or " ".join(segment.text for segment in segments).strip(), segments


def elevenlabs_result(payload: dict[str, Any], *, include_words: bool) -> tuple[str, list[ASRSegment]]:
    """Normalize both single- and multi-channel ElevenLabs STT responses."""
    transcripts = as_list(payload.get("transcripts"))
    if transcripts:
        parts = [_elevenlabs_single(as_mapping(item), include_words=include_words) for item in transcripts]
        text = " ".join(value[0] for value in parts if value[0]).strip()
        segments = [segment for _, result_segments in parts for segment in result_segments]
        return text, segments
    return _elevenlabs_single(payload, include_words=include_words)


def _elevenlabs_single(payload: dict[str, Any], *, include_words: bool) -> tuple[str, list[ASRSegment]]:
    text = str(payload.get("text", "")).strip()
    words = [
        word
        for raw_word in as_list(payload.get("words"))
        if isinstance(raw_word, dict)
        and str(raw_word.get("type", "word")).lower() in {"word", ""}
        and (word := word_from_mapping(raw_word, text_keys=("text", "word")))
    ]
    if words:
        start = min((word.start for word in words if word.start is not None), default=0.0)
        end = max((word.end for word in words if word.end is not None), default=start)
        return text or " ".join(word.text for word in words), [
            ASRSegment(text=text or " ".join(word.text for word in words), start=start, end=end, words=words if include_words else [])
        ]
    return text, [ASRSegment(text=text)] if text else []


def _seconds(item: dict[str, Any], prefix: str) -> float | None:
    """Read seconds, millisecond, and Azure-style timing fields safely."""
    direct = item.get(prefix)
    if direct is not None:
        return number(direct)
    milliseconds = item.get(f"{prefix}Milliseconds")
    if milliseconds is not None:
        return number(milliseconds) / 1000
    ticks = item.get(f"{prefix}InTicks") or item.get(f"{prefix}Ticks")
    if ticks is not None:
        return number(ticks) / 10_000_000
    return None
