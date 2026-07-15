from abc import ABC, abstractmethod
from typing import Any


class ASRProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str, *, word_timestamps: bool = False) -> list[dict[str, Any]]: ...

    def transcribe_text(self, audio_path: str) -> str:
        return " ".join(str(item.get("text", "")).strip() for item in self.transcribe(audio_path) if item.get("text")).strip()

    @abstractmethod
    def test_connection(self) -> str: ...
