from __future__ import annotations

from typing import Any, Dict, Iterable, List


END_PUNCTUATION = (".", "!", "?", "\u3002", "\uff01", "\uff1f")
MAX_DURATION = 8.0
MAX_SEGMENTS_PER_SENTENCE = 3


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _iter_valid_word_timestamps(segments: Iterable[Dict[str, Any]]) -> Iterable[tuple[float, float]]:
    for segment in segments:
        words = segment.get("words") or []
        for word in words:
            text = str(word.get("word", "")).strip()
            if not text:
                continue

            start_time = _to_float(word.get("start"))
            end_time = _to_float(word.get("end"))
            if start_time is None or end_time is None:
                continue
            if end_time <= start_time:
                continue
            yield start_time, end_time


def extract_sentence_effective_word_bounds(
    segments: Iterable[Dict[str, Any]],
) -> tuple[float | None, float | None]:
    first_word_start: float | None = None
    last_word_end: float | None = None

    for start_time, end_time in _iter_valid_word_timestamps(segments):
        if first_word_start is None:
            first_word_start = start_time
        last_word_end = end_time

    return first_word_start, last_word_end


# segment the ASR output into sentences based on punctuation and duration heuristics
def segment_to_sentences(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not segments:
        return []

    sentences: List[Dict[str, Any]] = []
    buffer: List[Dict[str, Any]] = []

    def flush_buffer() -> None:
        if not buffer:
            return
        word_start_time, word_end_time = extract_sentence_effective_word_bounds(buffer)
        sentence = {
            "start_time": buffer[0]["start"],
            "end_time": buffer[-1]["end"],
            "source_text": " ".join(item["text"] for item in buffer).strip(),
            "word_start_time": word_start_time,
            "word_end_time": word_end_time,
        }
        sentences.append(sentence)
        buffer.clear()

    for segment in segments:
        buffer.append(segment)
        duration = buffer[-1]["end"] - buffer[0]["start"]
        text = buffer[-1]["text"].strip()
        should_split = (
            text.endswith(END_PUNCTUATION)
            or duration >= MAX_DURATION
            or len(buffer) >= MAX_SEGMENTS_PER_SENTENCE
        )
        if should_split:
            flush_buffer()

    flush_buffer()

    for index, sentence in enumerate(sentences):
        sentence["display_order"] = index + 1

    return sentences
