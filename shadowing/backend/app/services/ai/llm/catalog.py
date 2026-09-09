"""The deliberately small, supported LLM adapter catalog."""

from app.services.ai.adapter_registry import AdapterConfigField, AdapterDescriptor, AdapterTestStrategy, register_adapter
from app.services.ai.audio_types import ProviderCapability
from app.services.ai.llm.openai_chat_compatible import OpenAIChatCompatibleLLMProvider
from app.services.ai.llm.openai_responses import OpenAIResponsesLLMProvider


LLM_CAPABILITIES = frozenset({ProviderCapability.GENERATE_TEXT, ProviderCapability.GENERATE_JSON})
TEXT_ONLY_CAPABILITIES = frozenset({ProviderCapability.GENERATE_TEXT})

LLM_ADAPTER_DESCRIPTORS = (
    AdapterDescriptor(
        canonical_key="openai_chat_compatible",
        kind="llm",
        adapter_class=OpenAIChatCompatibleLLMProvider,
        capabilities=LLM_CAPABILITIES,
        format_options=("json_schema", "response_format", "prompt_only"),
        preset_defaults={"base_url": "https://api.openai.com/v1", "enabled_capabilities": ["generate_text", "generate_json"], "enabled_formats": ["response_format"]},
        label="OpenAI Chat Completions",
        endpoint_mode="base_url",
        endpoint_hint="https://api.openai.com/v1  (adds /chat/completions)",
        config_fields=(
            AdapterConfigField("json_schema_name", "JSON schema name", default="response"),
            AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="bearer", options=("bearer", "api-key", "none")),
        ),
        docs_url="https://platform.openai.com/docs/api-reference/chat",
        test_strategy=AdapterTestStrategy(mode="metadata_http", label="List models", method="GET", endpoint_hint="/models", description="Checks metadata only; it never creates a completion."),
    ),
    AdapterDescriptor(
        canonical_key="openai_responses",
        kind="llm",
        adapter_class=OpenAIResponsesLLMProvider,
        capabilities=LLM_CAPABILITIES,
        format_options=("json_schema", "json_object", "prompt_only"),
        preset_defaults={"base_url": "https://api.openai.com/v1", "enabled_capabilities": ["generate_text", "generate_json"], "enabled_formats": ["json_schema"]},
        label="OpenAI Responses",
        endpoint_mode="base_url",
        endpoint_hint="https://api.openai.com/v1  (adds /responses)",
        config_fields=(
            AdapterConfigField("json_schema_name", "JSON schema name", default="response"),
            AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="bearer", options=("bearer", "api-key", "none")),
        ),
        docs_url="https://platform.openai.com/docs/api-reference/responses/create",
        test_strategy=AdapterTestStrategy(mode="metadata_http", label="List models", method="GET", endpoint_hint="/models", description="Checks metadata only; it never creates a response."),
    ),
)

for _descriptor in LLM_ADAPTER_DESCRIPTORS:
    register_adapter(_descriptor)

__all__ = ["LLM_ADAPTER_DESCRIPTORS", "LLM_CAPABILITIES", "TEXT_ONLY_CAPABILITIES"]
