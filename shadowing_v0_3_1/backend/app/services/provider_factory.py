import json
from typing import Any

from sqlmodel import Session, select

from app.models.ai_provider import AIProvider
from app.core.config import settings
from app.services.ai.audio_types import ProviderCapability
from app.services.ai.asr import AzureSpeechASRProvider, MiMoASRProvider, OpenAICompatibleRemoteASRProvider
from app.services.ai.llm import OpenAICompatibleLLMProvider
from app.services.ai.tts import AzureSpeechTTSProvider, MiMoTTSProvider, OpenAICompatibleTTSProvider


class ProviderConfigurationError(RuntimeError):
    pass


def get_declared_capabilities(provider: AIProvider) -> frozenset[ProviderCapability]:
    """Return Adapter-declared capabilities without making a network call."""
    provider_type = provider.provider_type.strip().lower()
    if provider.capability == "llm" and provider_type in {"openai_compatible", "openai-compatible", "openai"}:
        return OpenAICompatibleLLMProvider.capabilities
    if provider.capability == "tts" and provider_type in {"openai_compatible", "openai-compatible", "openai"}:
        return OpenAICompatibleTTSProvider.capabilities
    if provider.capability == "asr" and provider_type in {"openai_compatible", "openai-compatible", "openai"}:
        return OpenAICompatibleRemoteASRProvider.capabilities
    if provider.capability == "tts" and provider_type in {"azure_speech", "azure-speech"}:
        return AzureSpeechTTSProvider.capabilities
    if provider.capability == "asr" and provider_type in {"azure_speech", "azure-speech"}:
        return AzureSpeechASRProvider.capabilities
    if provider.capability == "tts" and provider_type in {"mimo_tts", "mimo-tts"}:
        return MiMoTTSProvider.capabilities
    if provider.capability == "asr" and provider_type in {"mimo_asr", "mimo-asr"}:
        return MiMoASRProvider.capabilities
    return frozenset()


def require_provider_capabilities(
    session: Session,
    capability: str,
    required: set[ProviderCapability],
    provider_id: int | None = None,
) -> AIProvider:
    provider = get_provider_record(session, capability, provider_id)
    missing = required - get_declared_capabilities(provider)
    if missing:
        values = ", ".join(sorted(item.value for item in missing))
        raise ProviderConfigurationError(
            f"Provider '{provider.name}' does not support required capabilities: {values}."
        )
    return provider


def parse_extra_config(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def get_provider_record(session: Session, capability: str, provider_id: int | None = None) -> AIProvider:
    statement = select(AIProvider).where(AIProvider.capability == capability, AIProvider.is_enabled == True)  # noqa: E712
    if provider_id is not None:
        provider = session.get(AIProvider, provider_id)
        if not provider or provider.capability != capability or not provider.is_enabled:
            raise ProviderConfigurationError(f"No enabled {capability.upper()} provider is available.")
        return provider
    provider = session.exec(statement.where(AIProvider.is_default == True).order_by(AIProvider.id)).first()  # noqa: E712
    if not provider:
        raise ProviderConfigurationError(f"No default enabled {capability.upper()} provider is configured.")
    return provider


def create_provider(provider: AIProvider):
    provider_type = provider.provider_type.strip().lower()
    extra = parse_extra_config(provider.extra_config)
    base_url, api_key, model_name = provider.base_url or "", provider.api_key or "", provider.model_name or ""
    if not base_url or not model_name:
        raise ProviderConfigurationError("Provider base URL and model name are required.")
    if provider.capability == "llm" and provider_type in {"openai_compatible", "openai-compatible", "openai"}:
        return OpenAICompatibleLLMProvider(base_url=base_url, api_key=api_key, model_name=model_name)
    if provider.capability == "tts" and provider_type in {"openai_compatible", "openai-compatible", "openai"}:
        return OpenAICompatibleTTSProvider(base_url=base_url, api_key=api_key, model_name=model_name, extra_config=extra)
    if provider.capability == "asr" and provider_type in {"openai_compatible", "openai-compatible", "openai"}:
        return OpenAICompatibleRemoteASRProvider(base_url=base_url, api_key=api_key, model_name=model_name, extra_config=extra)
    if provider.capability == "tts" and provider_type in {"azure_speech", "azure-speech"}:
        return AzureSpeechTTSProvider(base_url=base_url, api_key=api_key, model_name=model_name, extra_config=extra)
    if provider.capability == "asr" and provider_type in {"azure_speech", "azure-speech"}:
        return AzureSpeechASRProvider(base_url=base_url, api_key=api_key, model_name=model_name, extra_config=extra)
    if provider.capability == "tts" and provider_type in {"mimo_tts", "mimo-tts"}:
        return MiMoTTSProvider(base_url=base_url, api_key=api_key, model_name=model_name, extra_config=extra)
    if provider.capability == "asr" and provider_type in {"mimo_asr", "mimo-asr"}:
        return MiMoASRProvider(base_url=base_url, api_key=api_key, model_name=model_name, extra_config=extra)
    raise ProviderConfigurationError(f"Unsupported capability: {provider.capability}.")


def get_provider(session: Session, capability: str, provider_id: int | None = None):
    return create_provider(get_provider_record(session, capability, provider_id))


def get_llm_provider_with_legacy_fallback(session: Session):
    """Keep existing DeepSeek environment settings working during migration."""
    try:
        return get_provider(session, "llm")
    except ProviderConfigurationError:
        if settings.deepseek_api_key:
            return OpenAICompatibleLLMProvider(
                base_url=settings.deepseek_base_url,
                api_key=settings.deepseek_api_key,
                model_name=settings.deepseek_model,
            )
        raise
