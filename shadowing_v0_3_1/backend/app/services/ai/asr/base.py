from abc import ABC, abstractmethod

from app.services.ai.audio_types import ASRResult, AudioCapability, UnsupportedAudioCapabilityError


class ASRProvider(ABC):
    capabilities: frozenset[AudioCapability] = frozenset({AudioCapability.TRANSCRIBE})

    def supports(self, capability: AudioCapability) -> bool:
        return capability in self.capabilities

    @abstractmethod
    def transcribe(self, audio_path: str, *, word_timestamps: bool = False) -> ASRResult: ...

    def transcribe_text(self, audio_path: str) -> str:
        return self.transcribe(audio_path).text

    def require(self, capability: AudioCapability) -> None:
        if not self.supports(capability):
            raise UnsupportedAudioCapabilityError(f"This ASR provider does not support {capability.value}.")

    @abstractmethod
    def test_connection(self) -> str: ...
