from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.services.ai.audio_types import AudioCapability, TTSResult


@dataclass(frozen=True)
class TTSRequest:
    text: str
    voice: str | None = None
    model: str | None = None
    speed: float = 1.0
    accent: str | None = None
    gender: str | None = None


class TTSProvider(ABC):
    capabilities: frozenset[AudioCapability] = frozenset({AudioCapability.SYNTHESIZE})

    def supports(self, capability: AudioCapability) -> bool:
        return capability in self.capabilities

    @abstractmethod
    def synthesize(self, request: TTSRequest) -> TTSResult: ...

    @abstractmethod
    def list_voices(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def test_connection(self) -> str: ...
