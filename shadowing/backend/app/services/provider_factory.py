"""Provider construction and validation backed by the static adapter registry."""

from __future__ import annotations

import inspect
import json
from typing import Any, Mapping

from sqlmodel import Session, select

from app.models.ai_provider import AIProvider
from app.services.ai.adapter_registry import AdapterDescriptor, get_adapter_descriptor
from app.services.ai.audio_types import ProviderCapability


class ProviderConfigurationError(RuntimeError):
    """A safe, actionable error caused by a provider configuration."""


def parse_extra_config(raw: str | None) -> dict[str, Any]:
    """Parse legacy JSON safely; malformed historic rows behave as empty config."""
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def parse_string_list(raw: str | None) -> set[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return set()
    return {str(item).strip().lower() for item in value if str(item).strip()} if isinstance(value, list) else set()


def _preferred_format(capability: str, formats: set[str]) -> str | None:
    order = ("json_schema", "response_format", "prompt_only") if capability == "llm" else ("wav", "mp3", "flac", "opus", "aac", "pcm", "pcm16")
    return next((item for item in order if item in formats), None)


def validate_provider_boundaries(descriptor: AdapterDescriptor, capability: str, enabled_capabilities: set[str], enabled_formats: set[str]) -> tuple[set[str], set[str]]:
    available_capabilities = {item.value for item in descriptor.capabilities}
    unknown = enabled_capabilities - available_capabilities
    if unknown:
        raise ProviderConfigurationError("Unsupported enabled capability/capabilities: " + ", ".join(sorted(unknown)) + ".")
    available_formats = set(descriptor.format_options)
    unknown_formats = enabled_formats - available_formats
    if unknown_formats:
        raise ProviderConfigurationError("Unsupported enabled format(s): " + ", ".join(sorted(unknown_formats)) + ".")
    if ProviderCapability.WORD_TIMESTAMPS.value in enabled_capabilities and ProviderCapability.TRANSCRIBE.value not in enabled_capabilities:
        raise ProviderConfigurationError("word_timestamps requires transcribe.")
    if capability == "llm" and ProviderCapability.GENERATE_JSON.value in enabled_capabilities and not enabled_formats:
        raise ProviderConfigurationError("generate_json requires at least one JSON output format.")
    if capability == "tts" and ProviderCapability.SYNTHESIZE.value in enabled_capabilities and not enabled_formats:
        raise ProviderConfigurationError("synthesize requires at least one output format.")
    if capability == "asr" and enabled_formats:
        raise ProviderConfigurationError("ASR does not accept output formats.")
    return enabled_capabilities, enabled_formats


def get_provider_descriptor(capability: str, provider_type: str | None) -> AdapterDescriptor:
    descriptor = get_adapter_descriptor(capability, provider_type)
    if descriptor is None:
        type_label = (provider_type or "").strip() or "(blank)"
        raise ProviderConfigurationError(
            f"Unsupported {capability.upper()} adapter type: {type_label}."
        )
    return descriptor


def _field_value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def descriptor_config_fields(descriptor: AdapterDescriptor) -> tuple[dict[str, Any], ...]:
    """Return a normalized, non-secret field list for validation and reads."""
    fields: list[dict[str, Any]] = []
    for field in descriptor.config_fields:
        key = str(_field_value(field, "key", "")).strip()
        if not key:
            continue
        fields.append({
            "key": key,
            "required": bool(_field_value(field, "required", False)),
        })
    return tuple(fields)


def public_extra_config(descriptor: AdapterDescriptor, extra_config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project provider JSON to declared public fields only.

    Historic rows may contain arbitrary configuration from prior versions.  It
    remains usable by an adapter if necessary, but neither API reads nor new
    writes turn unknown values into an accidental credential leak.
    """
    raw = dict(extra_config or {})
    allowed = {field["key"] for field in descriptor_config_fields(descriptor)}
    return {key: value for key, value in raw.items() if key in allowed}


def validate_extra_config(
    descriptor: AdapterDescriptor,
    extra_config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    raw = dict(extra_config or {})
    fields = descriptor_config_fields(descriptor)
    allowed = {field["key"] for field in fields}
    unknown = sorted(key for key in raw if key not in allowed)
    if unknown:
        raise ProviderConfigurationError(
            "Unsupported adapter configuration field(s): " + ", ".join(unknown) + "."
        )
    for field in fields:
        value = raw.get(field["key"])
        missing = value is None or (isinstance(value, str) and not value.strip())
        if field["required"] and missing:
            raise ProviderConfigurationError(
                f"Adapter configuration field '{field['key']}' is required."
            )
    return raw


def validate_provider_configuration(
    *,
    capability: str,
    provider_type: str,
    base_url: str | None,
    api_key: str | None,
    model_name: str | None,
    extra_config: Mapping[str, Any] | None,
    enabled_capabilities: set[str] | None = None,
    enabled_formats: set[str] | None = None,
) -> tuple[AdapterDescriptor, dict[str, Any]]:
    """Validate only fields required by the chosen adapter descriptor."""
    descriptor = get_provider_descriptor(capability, provider_type)
    values = {
        "base_url": (base_url or "").strip(),
        "api_key": (api_key or "").strip(),
        "model_name": (model_name or "").strip(),
    }
    for field in descriptor.required_fields:
        if not values.get(field, ""):
            label = field.replace("_", " ")
            raise ProviderConfigurationError(
                f"{descriptor.label or descriptor.canonical_key}: {label} is required."
            )
    extra = validate_extra_config(descriptor, extra_config)
    capabilities = enabled_capabilities if enabled_capabilities is not None else {item.value for item in descriptor.capabilities}
    formats = enabled_formats if enabled_formats is not None else set(descriptor.format_options)
    validate_provider_boundaries(descriptor, capability, capabilities, formats)
    selected = _preferred_format(capability, formats)
    if selected:
        if capability == "llm": extra["json_mode"] = selected
        elif descriptor.canonical_key == "openai_audio_tts": extra["response_format"] = selected
        elif descriptor.canonical_key == "mimo_tts": extra["audio_format"] = selected
    return descriptor, extra


def get_declared_capabilities(provider: AIProvider) -> frozenset[ProviderCapability]:
    """Return Adapter-declared capabilities without making a network call."""
    descriptor = get_adapter_descriptor(provider.capability, provider.provider_type)
    return descriptor.capabilities if descriptor else frozenset()


def get_enabled_capabilities(provider: AIProvider) -> frozenset[ProviderCapability]:
    """Capabilities explicitly enabled by the user, never merely advertised."""
    descriptor = get_adapter_descriptor(provider.capability, provider.provider_type)
    if not descriptor:
        return frozenset()
    # Direct model construction in older tests is allowed pre-migration; real
    # migrated/API records always contain a JSON array.
    raw = getattr(provider, "enabled_capabilities", "")
    selected = {item.value for item in descriptor.capabilities} if raw in (None, "") else parse_string_list(raw)
    return frozenset(item for item in descriptor.capabilities if item.value in selected)


def require_provider_capabilities(
    session: Session,
    capability: str,
    required: set[ProviderCapability],
    provider_id: int | None = None,
) -> AIProvider:
    provider = get_provider_record(session, capability, provider_id)
    missing = required - get_enabled_capabilities(provider)
    if missing:
        values = ", ".join(sorted(item.value for item in missing))
        raise ProviderConfigurationError(
            f"Provider '{provider.name}' does not support required capabilities: {values}."
        )
    return provider


def get_provider_record(session: Session, capability: str, provider_id: int | None = None) -> AIProvider:
    statement = select(AIProvider).where(
        AIProvider.capability == capability,
        AIProvider.is_enabled == True,  # noqa: E712
    )
    if provider_id is not None:
        provider = session.get(AIProvider, provider_id)
        if not provider or provider.capability != capability or not provider.is_enabled:
            raise ProviderConfigurationError(f"No enabled {capability.upper()} provider is available.")
        return provider
    provider = session.exec(
        statement.where(AIProvider.is_default == True).order_by(AIProvider.id)  # noqa: E712
    ).first()
    if not provider:
        raise ProviderConfigurationError(f"No default enabled {capability.upper()} provider is configured.")
    return provider


def _create_from_descriptor(
    descriptor: AdapterDescriptor,
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    extra_config: dict[str, Any],
) -> Any:
    kwargs = {
        "base_url": base_url,
        "api_key": api_key,
        "model_name": model_name,
        "extra_config": extra_config,
    }
    implementation = descriptor.factory or descriptor.adapter_class
    if implementation is None:  # validated by the descriptor itself
        raise ProviderConfigurationError("Adapter has no implementation.")
    parameters = inspect.signature(implementation).parameters
    if "extra_config" not in parameters and not any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    ):
        kwargs.pop("extra_config")
    return descriptor.create(**kwargs)


def create_provider(provider: AIProvider):
    descriptor, extra = validate_provider_configuration(
        capability=provider.capability,
        provider_type=provider.provider_type,
        base_url=provider.base_url,
        api_key=provider.api_key,
        model_name=provider.model_name,
        # Historic records are parsed here; only create/update routes reject
        # unknown public config fields.  This preserves old working settings.
        extra_config=public_extra_config(
            get_provider_descriptor(provider.capability, provider.provider_type),
            parse_extra_config(provider.extra_config),
        ),
        enabled_capabilities=parse_string_list(getattr(provider, "enabled_capabilities", "")) if getattr(provider, "enabled_capabilities", "") not in (None, "") else None,
        enabled_formats=parse_string_list(getattr(provider, "enabled_formats", "")) if getattr(provider, "enabled_formats", "") not in (None, "") else None,
    )
    return _create_from_descriptor(
        descriptor,
        base_url=(provider.base_url or "").strip(),
        api_key=(provider.api_key or "").strip(),
        model_name=(provider.model_name or "").strip(),
        extra_config=extra,
    )


def get_provider(session: Session, capability: str, provider_id: int | None = None):
    return create_provider(get_provider_record(session, capability, provider_id))


__all__ = [
    "ProviderConfigurationError",
    "create_provider",
    "descriptor_config_fields",
    "get_declared_capabilities",
    "get_enabled_capabilities",
    "get_provider",
    "get_provider_descriptor",
    "get_provider_record",
    "parse_extra_config",
    "parse_string_list",
    "public_extra_config",
    "require_provider_capabilities",
    "validate_extra_config",
    "validate_provider_boundaries",
    "validate_provider_configuration",
]
