from abc import ABC, abstractmethod

from app.services.ai.audio_types import ASRResult, ProviderCapability, UnsupportedAudioCapabilityError


class UnsupportedASRLanguageError(ValueError):
    """Raised before a request when an adapter cannot accept a task language."""


def resolve_asr_language(
    language: str | None,
    extra_config: dict[str, object] | None = None,
) -> str | None:
    """Prefer an explicit task language over a provider-profile fallback."""
    explicit = str(language or "").strip()
    if explicit:
        return explicit
    configured = str((extra_config or {}).get("language") or "").strip()
    return configured or None


def openai_language_code(language: str | None) -> str | None:
    """Translate a BCP-47 tag to OpenAI transcription's base language code.

    OpenAI Audio transcription accepts ISO-639-1-style language codes.  The
    rest of the application stores canonical BCP-47 tags such as ``zh-CN``;
    reducing those to their primary subtag keeps task-level language metadata
    useful without leaking locale-specific formatting into the provider API.
    ``auto`` deliberately means omit the hint and let the provider detect it.
    """
    value = str(language or "").strip()
    if not value or value.casefold() == "auto":
        return None
    return value.replace("_", "-").split("-", 1)[0].casefold() or None


class ASRProvider(ABC):
    capabilities: frozenset[ProviderCapability] = frozenset({ProviderCapability.TRANSCRIBE})

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.capabilities

    def provider_language(self, language: str | None) -> str | None:
        """Map a task language into the provider's request vocabulary.

        Most OpenAI-compatible transcription endpoints accept a broad language
        set, so the base implementation preserves the task value.  Narrower
        adapters override this method and raise before any network request.
        """
        value = str(language or "").strip()
        return value or None

    def supports_language(self, language: str | None) -> bool:
        """Return whether an explicit task language is valid for this adapter."""
        if language is None or not str(language).strip():
            # Settings pages do not have a concrete material/recording language;
            # capability-only availability remains meaningful there.
            return True
        try:
            self.provider_language(language)
        except UnsupportedASRLanguageError:
            return False
        return True

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        *,
        word_timestamps: bool = False,
        language: str | None = None,
    ) -> ASRResult: ...

    def transcribe_text(self, audio_path: str, *, language: str | None = None) -> str:
        return self.transcribe(audio_path, language=language).text

    def require(self, capability: ProviderCapability) -> None:
        if not self.supports(capability):
            raise UnsupportedAudioCapabilityError(f"This ASR provider does not support {capability.value}.")

    @abstractmethod
    def test_connection(self) -> str: ...
