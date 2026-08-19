from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProviderCapability(StrEnum):
    GENERATE_TEXT = "generate_text"
    GENERATE_JSON = "generate_json"
    SYNTHESIZE = "synthesize"
    LIST_VOICES = "list_voices"
    TRANSCRIBE = "transcribe"
    WORD_TIMESTAMPS = "word_timestamps"


class UnsupportedAudioCapabilityError(ValueError):
    pass


@dataclass(frozen=True)
class RawPCMFormat:
    """The decoding contract for a headerless PCM response.

    Raw PCM has no container metadata.  Providers must attach this structure
    before a worker is allowed to turn it into a playable sentence clip.
    """

    sample_rate: int
    channels: int = 1
    sample_format: str = "s16le"

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("Raw PCM sample_rate must be positive.")
        if self.channels <= 0:
            raise ValueError("Raw PCM channels must be positive.")
        if self.sample_format not in {"s16le", "s24le", "s32le", "f32le"}:
            raise ValueError("Unsupported raw PCM sample format.")


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
    raw_pcm: RawPCMFormat | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)
