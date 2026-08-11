"""Static, side-effect-free metadata for pluggable AI provider adapters.

The registry intentionally describes adapters without constructing them or making
network requests.  It is the single place API code can use to resolve legacy
provider-type aliases, expose a safe catalog to clients, and discover declared
capabilities before credentials are tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Callable, Mapping

from app.services.ai.audio_types import ProviderCapability


AdapterFactory = Callable[..., Any]
PublicConfigField = "AdapterConfigField | Mapping[str, Any]"


def normalize_adapter_key(value: str) -> str:
    """Normalize user-entered provider types while retaining readable aliases."""
    return value.strip().lower().replace("-", "_")


@dataclass(frozen=True)
class AdapterConfigField:
    """A non-secret field that may be stored in a provider's ``extra_config``."""

    key: str
    label: str
    field_type: str = "string"
    required: bool = False
    default: Any = None
    options: tuple[str, ...] = ()
    placeholder: str = ""
    help_text: str = ""

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "key": self.key,
            "label": self.label,
            "field_type": self.field_type,
            "required": self.required,
            "options": list(self.options),
            "default": self.default,
            "placeholder": self.placeholder,
            "help_text": self.help_text,
        }
        return payload


@dataclass(frozen=True)
class AdapterTestStrategy:
    """Describe a connection test that must not trigger paid generation."""

    mode: str
    label: str
    no_cost: bool = True
    method: str | None = None
    endpoint_hint: str | None = None
    description: str = ""

    @property
    def verification_level(self) -> str:
        """API-facing summary: metadata HTTP checks are still network checks."""
        return "configuration" if self.mode == "configuration" else "network"

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "mode": self.mode,
            "label": self.label,
            "no_cost": self.no_cost,
            "verification_level": self.verification_level,
            "description": self.description,
        }
        if self.method:
            payload["method"] = self.method
        if self.endpoint_hint:
            payload["endpoint_hint"] = self.endpoint_hint
        return payload


@dataclass(frozen=True)
class AdapterDescriptor:
    """Static contract for one provider protocol adapter.

    ``config_fields`` deliberately excludes credentials.  Credentials belong in
    the provider record's dedicated fields, while catalog consumers can safely
    render these public knobs from ``extra_config``.
    """

    canonical_key: str
    kind: str
    adapter_class: type[Any] | None = None
    factory: AdapterFactory | None = None
    aliases: tuple[str, ...] = ()
    capabilities: frozenset[ProviderCapability] = frozenset()
    # Formats are protocol options, not promises: a saved provider must opt in
    # explicitly before the corresponding capability can be used.
    format_options: tuple[str, ...] = ()
    label: str = ""
    endpoint_mode: str = "base_url"
    endpoint_hint: str = ""
    required_fields: tuple[str, ...] = ("base_url", "api_key", "model_name")
    config_fields: tuple[PublicConfigField, ...] = ()
    voice_presets: tuple[Mapping[str, Any], ...] = ()
    docs_url: str | None = None
    test_strategy: AdapterTestStrategy | Mapping[str, Any] | str = field(
        default_factory=lambda: AdapterTestStrategy(
            mode="configuration",
            label="Configuration validation",
            no_cost=True,
            description="Validates required fields locally; no network request is made.",
        )
    )

    def __post_init__(self) -> None:
        if not normalize_adapter_key(self.canonical_key):
            raise ValueError("Adapter descriptors need a canonical key.")
        if not self.kind.strip():
            raise ValueError("Adapter descriptors need a kind.")
        if self.adapter_class is None and self.factory is None:
            raise ValueError("Adapter descriptors need an adapter class or factory.")
        if self.endpoint_mode not in {"base_url", "full_endpoint"}:
            raise ValueError("endpoint_mode must be 'base_url' or 'full_endpoint'.")
        secret_field_names = {"api_key", "apikey", "secret", "token", "password"}
        for config_field in self.config_fields:
            name = _config_field_key(config_field)
            if name and normalize_adapter_key(name) in secret_field_names:
                raise ValueError("Secret fields must not be exposed in adapter config_fields.")

    @property
    def key(self) -> str:
        """Short alias useful to catalog and factory callers."""
        return self.canonical_key

    @property
    def provider_type(self) -> str:
        """Backward-friendly name for the canonical persisted provider type."""
        return self.canonical_key

    @property
    def all_keys(self) -> tuple[str, ...]:
        return (self.canonical_key, *self.aliases)

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.capabilities

    def create(self, **kwargs: Any) -> Any:
        """Instantiate the adapter without giving the registry ownership of it."""
        implementation = self.factory or self.adapter_class
        if implementation is None:  # Defensive; validated by __post_init__.
            raise RuntimeError("Adapter descriptor has no implementation.")
        return implementation(**kwargs)

    def to_catalog_payload(self) -> dict[str, Any]:
        """Return JSON-safe metadata suitable for an unauthenticated UI catalog."""
        return {
            "key": self.canonical_key,
            "canonical_key": self.canonical_key,
            "provider_type": self.canonical_key,
            "kind": self.kind,
            "capability": self.kind,
            "label": self.label or self.canonical_key,
            "aliases": list(self.aliases),
            "capabilities": sorted(item.value for item in self.capabilities),
            "available_capabilities": sorted(item.value for item in self.capabilities),
            "available_formats": list(self.format_options),
            "endpoint_mode": self.endpoint_mode,
            "endpoint_hint": self.endpoint_hint,
            "required_fields": list(self.required_fields),
            "config_fields": [_config_field_payload(item) for item in self.config_fields],
            "voice_presets": [dict(item) for item in self.voice_presets],
            "docs_url": self.docs_url,
            "test_strategy": _test_strategy_payload(self.test_strategy),
        }


def _config_field_key(value: PublicConfigField) -> str:
    if isinstance(value, AdapterConfigField):
        return value.key
    return str(value.get("key", ""))


def _config_field_payload(value: PublicConfigField) -> dict[str, Any]:
    if isinstance(value, AdapterConfigField):
        return value.to_payload()
    payload = dict(value)
    # Accept simple mappings from future adapter families, while keeping the
    # catalog wire shape stable for the API schema and frontend form renderer.
    if "field_type" not in payload:
        payload["field_type"] = payload.pop("type", "string")
    if "help_text" not in payload:
        payload["help_text"] = payload.pop("description", "")
    payload.setdefault("required", False)
    options = payload.get("options", [])
    if isinstance(options, str):
        options = [options]
    elif not isinstance(options, list):
        options = list(options) if options else []
    payload["options"] = [str(option) for option in options]
    payload.setdefault("default", None)
    payload.setdefault("placeholder", "")
    return payload


def _test_strategy_payload(value: AdapterTestStrategy | Mapping[str, Any] | str) -> dict[str, Any] | str:
    if isinstance(value, AdapterTestStrategy):
        return value.to_payload()
    if isinstance(value, Mapping):
        return dict(value)
    return value


class AdapterRegistry:
    """In-memory registry keyed by (kind, canonical key or alias)."""

    def __init__(self) -> None:
        self._descriptors: dict[tuple[str, str], AdapterDescriptor] = {}
        self._order: list[AdapterDescriptor] = []

    def register(self, descriptor: AdapterDescriptor) -> AdapterDescriptor:
        kind = normalize_adapter_key(descriptor.kind)
        canonical = normalize_adapter_key(descriptor.canonical_key)
        existing = self._descriptors.get((kind, canonical))
        if existing is not None:
            if existing == descriptor:
                return existing
            raise ValueError(f"Adapter '{descriptor.kind}/{descriptor.canonical_key}' is already registered.")

        keys = {canonical, *(normalize_adapter_key(alias) for alias in descriptor.aliases)}
        for key in keys:
            if not key:
                raise ValueError("Adapter aliases cannot be blank.")
            collision = self._descriptors.get((kind, key))
            if collision is not None and collision != descriptor:
                raise ValueError(f"Adapter alias '{key}' is already registered for {descriptor.kind}.")

        self._order.append(descriptor)
        for key in keys:
            self._descriptors[(kind, key)] = descriptor
        return descriptor

    def get(self, kind: str, provider_type: str | None) -> AdapterDescriptor | None:
        if not provider_type:
            return None
        return self._descriptors.get((normalize_adapter_key(kind), normalize_adapter_key(provider_type)))

    def list(self, kind: str | None = None) -> tuple[AdapterDescriptor, ...]:
        if kind is None:
            return tuple(self._order)
        normalized_kind = normalize_adapter_key(kind)
        return tuple(item for item in self._order if normalize_adapter_key(item.kind) == normalized_kind)


adapter_registry = AdapterRegistry()
_builtins_loading = False
_builtins_loaded = False


def _ensure_builtin_adapters() -> None:
    """Load descriptor-only builtins lazily to avoid adapter import cycles."""
    global _builtins_loaded, _builtins_loading
    if _builtins_loaded or _builtins_loading:
        return
    _builtins_loading = True
    try:
        import_module("app.services.ai.llm.catalog")
        import_module("app.services.ai.audio_catalog")
        _builtins_loaded = True
    finally:
        _builtins_loading = False


def register_adapter(descriptor: AdapterDescriptor) -> AdapterDescriptor:
    """Register an adapter descriptor for factory and catalog consumers."""
    return adapter_registry.register(descriptor)


def get_adapter_descriptor(kind: str, provider_type: str | None) -> AdapterDescriptor | None:
    """Resolve a canonical key or legacy alias without creating an adapter."""
    _ensure_builtin_adapters()
    return adapter_registry.get(kind, provider_type)


def list_adapter_descriptors(kind: str | None = None) -> tuple[AdapterDescriptor, ...]:
    """List descriptors in registration order, optionally scoped to one kind."""
    _ensure_builtin_adapters()
    return adapter_registry.list(kind)


def catalog_payload(kind: str | None = None) -> list[dict[str, Any]]:
    """Return a UI-safe catalog.  It never contains API keys or other secrets."""
    return [descriptor.to_catalog_payload() for descriptor in list_adapter_descriptors(kind)]


__all__ = [
    "AdapterConfigField",
    "AdapterDescriptor",
    "AdapterFactory",
    "AdapterRegistry",
    "AdapterTestStrategy",
    "adapter_registry",
    "catalog_payload",
    "get_adapter_descriptor",
    "list_adapter_descriptors",
    "normalize_adapter_key",
    "register_adapter",
]
