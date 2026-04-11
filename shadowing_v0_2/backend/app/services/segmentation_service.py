from __future__ import annotations

from typing import Any, Dict, List


END_PUNCTUATION = (".", "!", "?", "。", "！", "？")
MAX_DURATION = 8.0
MAX_SEGMENTS_PER_SENTENCE = 3

# segment the ASR output into sentences based on punctuation and duration heuristics
def segment_to_sentences(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not segments:
        return []

    sentences: List[Dict[str, Any]] = []
    buffer: List[Dict[str, Any]] = []

    def flush_buffer():
        if not buffer:
            return
        sentence = {
            "start_time": buffer[0]["start"],
            "end_time": buffer[-1]["end"],
            "source_text": " ".join(item["text"] for item in buffer).strip(),
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
