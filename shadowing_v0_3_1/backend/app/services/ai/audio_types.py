from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AudioCapability(StrEnum):
    SYNTHESIZE = "synthesize"
    LIST_VOICES = "list_voices"
    TRANSCRIBE = "transcribe"
    WORD_TIMESTAMPS = "word_timestamps"


class UnsupportedAudioCapabilityError(ValueError):
    pass


@dataclass(frozen=True)
class ASRWord:
    text: str
    start: float | None = None
    end: float | None = None


@dataclass(frozen=True)
class ASRSegment:
    text: str
    start: float = 0.0
    end: float = 0.0
    words: list[ASRWord] = field(default_factory=list)


@dataclass(frozen=True)
class ASRResult:
    text: str
    segments: list[ASRSegment]
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def as_legacy_segments(self) -> list[dict[str, Any]]:
        return [
            {"start": segment.start, "end": segment.end, "text": segment.text,
             "words": [{"start": word.start, "end": word.end, "word": word.text} for word in segment.words]}
            for segment in self.segments
        ]


@dataclass(frozen=True)
class TTSResult:
    audio: bytes
    media_type: str = "audio/mpeg"
    extension: str = "mp3"
    provider_metadata: dict[str, Any] = field(default_factory=dict)
