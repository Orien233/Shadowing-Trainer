from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TTSRequest:
    text: str
    voice: str | None = None
    model: str | None = None
    speed: float = 1.0
    accent: str | None = None
    gender: str | None = None


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, request: TTSRequest) -> bytes: ...

    @abstractmethod
    def list_voices(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def test_connection(self) -> str: ...
