from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.services.ai.audio_types import AudioCapability, TTSResult, UnsupportedAudioCapabilityError


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

    def list_voices(self) -> list[dict[str, Any]]:
        """Return provider metadata only when ``list_voices`` is declared.

        Static voice presets belong to an adapter descriptor, not to this
        method.  That distinction prevents the UI from treating a locally
        configured list as a live vendor voice catalog.
        """
        if not self.supports(AudioCapability.LIST_VOICES):
            raise UnsupportedAudioCapabilityError(
                "This TTS provider does not support list_voices."
            )
        return []

    @abstractmethod
    def test_connection(self) -> str: ...
