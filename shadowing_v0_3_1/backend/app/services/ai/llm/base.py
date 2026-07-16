from abc import ABC, abstractmethod
from typing import Any

from app.services.ai.audio_types import ProviderCapability


class LLMProvider(ABC):
    capabilities: frozenset[ProviderCapability] = frozenset({
        ProviderCapability.GENERATE_TEXT,
        ProviderCapability.GENERATE_JSON,
    })

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.capabilities
    @abstractmethod
    def generate_text(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str: ...

    @abstractmethod
    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict[str, Any]: ...

    @abstractmethod
    def test_connection(self) -> str: ...
