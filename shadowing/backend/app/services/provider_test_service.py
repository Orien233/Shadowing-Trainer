from __future__ import annotations

import tempfile
import wave
from pathlib import Path
from typing import Any, Mapping

from app.models.ai_provider import AIProvider
from app.schemas.ai_provider import ProviderTestResponse, ProviderVoiceRead
from app.services.ai.adapter_registry import AdapterDescriptor
from app.services.ai.audio_types import ProviderCapability
from app.services.ai.tts.base import TTSRequest
from app.services.provider_factory import (
    ProviderConfigurationError,
    create_provider,
    get_enabled_capabilities,
    get_provider_descriptor,
    parse_string_list,
)
from app.services.provider_security import redact_provider_error


def _verification_level(descriptor: AdapterDescriptor) -> str:
    strategy = descriptor.test_strategy
    value: Any = getattr(strategy, "verification_level", None)
    if value is None and isinstance(strategy, Mapping):
        value = strategy.get("verification_level")
    return "network" if value == "network" else "configuration"


def _test_response(
    *,
    provider: AIProvider,
    descriptor: AdapterDescriptor,
    ok: bool,
    message: str,
    verification_level: str,
    billable: bool = False,
) -> ProviderTestResponse:
    capabilities = sorted(item.value for item in get_enabled_capabilities(provider))
    return ProviderTestResponse(
        ok=ok,
        message=message,
        capabilities=capabilities,
        available_capabilities=sorted(item.value for item in descriptor.capabilities),
        enabled_capabilities=capabilities,
        available_formats=list(descriptor.format_options),
        enabled_formats=sorted(parse_string_list(provider.enabled_formats)),
        verification_level=verification_level,
        billable=billable,
    )


def _write_silent_wav() -> Path:
    """Create a minimal safe ASR test input without using user recordings."""
    handle = tempfile.NamedTemporaryFile(
        prefix="shadowing-asr-test-",
        suffix=".wav",
        delete=False,
    )
    path = Path(handle.name)
    handle.close()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x00\x00" * 3200)
    return path


def _run_inference_test(provider: AIProvider, instance: Any) -> str:
    capabilities = get_enabled_capabilities(provider)
    if provider.capability == "llm":
        if ProviderCapability.GENERATE_TEXT not in capabilities:
            raise ProviderConfigurationError(
                "A live LLM test requires generate_text to be enabled."
            )
        instance.generate_text(
            system_prompt="You are a connection test. Respond with exactly OK.",
            user_prompt="Return OK.",
            temperature=0,
        )
        return "A small live LLM generation request succeeded."
    if provider.capability == "tts":
        if ProviderCapability.SYNTHESIZE not in capabilities:
            raise ProviderConfigurationError(
                "A live TTS test requires synthesize to be enabled."
            )
        result = instance.synthesize(
            TTSRequest(text="Connection test.", model=provider.model_name or None)
        )
        if not result.audio:
            raise ProviderConfigurationError("The provider returned empty test audio.")
        return "A small live TTS synthesis request succeeded."
    if provider.capability == "asr":
        if ProviderCapability.TRANSCRIBE not in capabilities:
            raise ProviderConfigurationError(
                "A live ASR test requires transcribe to be enabled."
            )
        path = _write_silent_wav()
        try:
            instance.transcribe(str(path))
        finally:
            path.unlink(missing_ok=True)
        return "A small live ASR transcription request succeeded."
    raise ProviderConfigurationError(
        "Unsupported provider capability for a live test."
    )


def test_provider(
    provider: AIProvider,
    test_mode: str = "configuration",
) -> ProviderTestResponse:
    descriptor = get_provider_descriptor(provider.capability, provider.provider_type)
    try:
        instance = create_provider(provider)
        if test_mode == "configuration":
            return _test_response(
                provider=provider,
                descriptor=descriptor,
                ok=True,
                message=(
                    "Provider configuration is valid; no network or billable "
                    "request was made."
                ),
                verification_level="configuration",
            )
        if test_mode == "network":
            return _test_response(
                provider=provider,
                descriptor=descriptor,
                ok=True,
                message=instance.test_connection(),
                verification_level=_verification_level(descriptor),
            )
        if test_mode == "inference":
            return _test_response(
                provider=provider,
                descriptor=descriptor,
                ok=True,
                message=_run_inference_test(provider, instance),
                verification_level="inference",
                billable=True,
            )
        raise ProviderConfigurationError(
            f"Unsupported provider test mode: {test_mode}."
        )
    except Exception as exc:
        verification_level = (
            "inference"
            if test_mode == "inference"
            else _verification_level(descriptor)
            if test_mode == "network"
            else "configuration"
        )
        return _test_response(
            provider=provider,
            descriptor=descriptor,
            ok=False,
            message=(
                f"{test_mode.capitalize()} test failed: {type(exc).__name__}: "
                f"{redact_provider_error(exc, provider.api_key)}"
            ),
            verification_level=verification_level,
            billable=test_mode == "inference",
        )


def voice_to_read(item: Mapping[str, Any]) -> ProviderVoiceRead:
    locale = item.get("locale")
    languages = item.get("languages")
    if not isinstance(languages, list):
        languages = [str(locale)] if locale else []
    styles = item.get("styles")
    metadata = item.get("provider_metadata")
    return ProviderVoiceRead(
        id=str(item.get("id", "")),
        name=str(item.get("name") or item.get("id") or ""),
        languages=[str(value) for value in languages if str(value).strip()],
        gender=str(item["gender"]) if item.get("gender") else None,
        accent=str(item["accent"]) if item.get("accent") else None,
        styles=(
            [str(value) for value in styles if str(value).strip()]
            if isinstance(styles, list)
            else []
        ),
        preview_url=(
            str(item["preview_url"]) if item.get("preview_url") else None
        ),
        provider_metadata=dict(metadata) if isinstance(metadata, dict) else {},
    )
