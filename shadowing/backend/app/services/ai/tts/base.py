from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.services.ai.audio_types import ProviderCapability, TTSResult, UnsupportedAudioCapabilityError


@dataclass(frozen=True)
class TTSRequest:
    text: str
    # Canonical BCP-47 language tag for the text being spoken.  Adapters map
    # this context to their own request shape (or instructions) instead of
    # assuming the application UI language.
    language: str | None = None
    voice: str | None = None
    model: str | None = None
    speed: float = 1.0
    accent: str | None = None
    gender: str | None = None


class TTSProvider(ABC):
    capabilities: frozenset[ProviderCapability] = frozenset({ProviderCapability.SYNTHESIZE})

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.capabilities

    @abstractmethod
    def synthesize(self, request: TTSRequest) -> TTSResult: ...

    def list_voices(self) -> list[dict[str, Any]]:
        """Return provider metadata only when ``list_voices`` is declared.

        Static voice presets belong to an adapter descriptor, not to this
        method.  That distinction prevents the UI from treating a locally
        configured list as a live vendor voice catalog.
        """
        if not self.supports(ProviderCapability.LIST_VOICES):
            raise UnsupportedAudioCapabilityError(
                "This TTS provider does not support list_voices."
            )
        return []

    @abstractmethod
    def test_connection(self) -> str: ...
