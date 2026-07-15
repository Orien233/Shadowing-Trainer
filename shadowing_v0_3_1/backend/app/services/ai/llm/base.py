from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @abstractmethod
    def generate_text(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str: ...

    @abstractmethod
    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict[str, Any]: ...

    @abstractmethod
    def test_connection(self) -> str: ...
