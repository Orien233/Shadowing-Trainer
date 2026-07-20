"""Static catalog entries for the project's LLM protocol adapters."""

from app.services.ai.adapter_registry import (
    AdapterConfigField,
    AdapterDescriptor,
    AdapterTestStrategy,
    register_adapter,
)
from app.services.ai.audio_types import ProviderCapability
from app.services.ai.llm.anthropic_messages import AnthropicMessagesLLMProvider
from app.services.ai.llm.gemini_generate_content import GeminiGenerateContentLLMProvider
from app.services.ai.llm.openai_chat_compatible import OpenAIChatCompatibleLLMProvider
from app.services.ai.llm.openai_responses import OpenAIResponsesLLMProvider


LLM_CAPABILITIES = frozenset({
    ProviderCapability.GENERATE_TEXT,
    ProviderCapability.GENERATE_JSON,
})
TEXT_ONLY_CAPABILITIES = frozenset({ProviderCapability.GENERATE_TEXT})

_MODE_OPTIONS = ("response_format", "json_schema", "prompt_only")

LLM_ADAPTER_DESCRIPTORS = (
    AdapterDescriptor(
        canonical_key="openai_chat_compatible",
        kind="llm",
        adapter_class=OpenAIChatCompatibleLLMProvider,
        aliases=("openai_compatible", "openai-compatible", "openai"),
        capabilities=LLM_CAPABILITIES,
        label="OpenAI-compatible Chat Completions",
        endpoint_mode="base_url",
        endpoint_hint="https://api.openai.com/v1  (the adapter adds /chat/completions)",
        config_fields=(
            AdapterConfigField(
                key="json_mode",
                label="JSON mode",
                field_type="select",
                default="response_format",
                options=_MODE_OPTIONS,
                help_text="Use the provider's response_format, a JSON Schema when supported, or prompt-only JSON.",
            ),
            AdapterConfigField(
                key="json_schema_name",
                label="JSON schema name",
                default="response",
                placeholder="response",
                help_text="Used only when JSON mode is json_schema.",
            ),
            AdapterConfigField(
                key="auth_scheme",
                label="Authentication scheme",
                field_type="select",
                default="bearer",
                options=("bearer", "api-key", "none"),
                help_text="Use none for a local Ollama/vLLM server without authentication.",
            ),
        ),
        docs_url="https://platform.openai.com/docs/api-reference/chat",
        test_strategy=AdapterTestStrategy(
            mode="metadata_http",
            label="List models",
            method="GET",
            endpoint_hint="/models",
            description="Checks credentials against the provider metadata endpoint; it never sends a completion request.",
        ),
    ),
    AdapterDescriptor(
        canonical_key="openai_responses",
        kind="llm",
        adapter_class=OpenAIResponsesLLMProvider,
        aliases=("openai-responses", "responses"),
        capabilities=LLM_CAPABILITIES,
        label="OpenAI Responses API",
        endpoint_mode="base_url",
        endpoint_hint="https://api.openai.com/v1  (the adapter adds /responses)",
        config_fields=(
            AdapterConfigField(
                key="json_mode",
                label="JSON mode",
                field_type="select",
                default="json_object",
                options=("json_object", "json_schema", "prompt_only"),
                help_text="Select JSON object mode, JSON Schema mode, or prompt-only JSON.",
            ),
            AdapterConfigField(
                key="json_schema_name",
                label="JSON schema name",
                default="response",
                placeholder="response",
                help_text="Used only when JSON mode is json_schema.",
            ),
            AdapterConfigField(
                key="max_output_tokens",
                label="Maximum output tokens",
                field_type="number",
                placeholder="1024",
                help_text="Optional Responses API output limit.",
            ),
            AdapterConfigField(
                key="auth_scheme",
                label="Authentication scheme",
                field_type="select",
                default="bearer",
                options=("bearer", "api-key", "none"),
            ),
        ),
        docs_url="https://platform.openai.com/docs/api-reference/responses",
        test_strategy=AdapterTestStrategy(
            mode="metadata_http",
            label="List models",
            method="GET",
            endpoint_hint="/models",
            description="Checks credentials against the provider metadata endpoint; it never sends a response-generation request.",
        ),
    ),
    AdapterDescriptor(
        canonical_key="anthropic_messages",
        kind="llm",
        adapter_class=AnthropicMessagesLLMProvider,
        aliases=("anthropic-messages", "anthropic"),
        capabilities=LLM_CAPABILITIES,
        label="Anthropic Messages API",
        endpoint_mode="base_url",
        endpoint_hint="https://api.anthropic.com/v1  (the adapter adds /messages)",
        config_fields=(
            AdapterConfigField(
                key="api_version",
                label="Anthropic API version",
                default="2023-06-01",
                placeholder="2023-06-01",
                help_text="Sent as the anthropic-version request header.",
            ),
            AdapterConfigField(
                key="max_tokens",
                label="Maximum output tokens",
                field_type="number",
                default=1024,
                placeholder="1024",
                help_text="Required by the Messages API; 1024 is used when left unset.",
            ),
            AdapterConfigField(
                key="json_mode",
                label="JSON mode",
                field_type="select",
                default="prompt_only",
                options=("prompt_only",),
                help_text="JSON is prompt-enforced so it works across Messages API model versions.",
            ),
        ),
        docs_url="https://docs.anthropic.com/en/api/messages",
        test_strategy=AdapterTestStrategy(
            mode="metadata_http",
            label="List models",
            method="GET",
            endpoint_hint="/models",
            description="Checks credentials against Anthropic's model metadata endpoint; it never creates a message.",
        ),
    ),
    AdapterDescriptor(
        canonical_key="gemini_generate_content",
        kind="llm",
        adapter_class=GeminiGenerateContentLLMProvider,
        aliases=("gemini-generate-content", "gemini"),
        capabilities=LLM_CAPABILITIES,
        label="Gemini Generate Content API",
        endpoint_mode="base_url",
        endpoint_hint="https://generativelanguage.googleapis.com/v1beta  (the adapter adds /models/{model}:generateContent)",
        config_fields=(
            AdapterConfigField(
                key="api_version",
                label="Gemini API version",
                default="v1beta",
                placeholder="v1beta",
                help_text="Appended only when the configured base URL does not already end in this API version.",
            ),
            AdapterConfigField(
                key="max_output_tokens",
                label="Maximum output tokens",
                field_type="number",
                placeholder="1024",
                help_text="Optional Gemini generationConfig.maxOutputTokens setting.",
            ),
        ),
        docs_url="https://ai.google.dev/api/generate-content",
        test_strategy=AdapterTestStrategy(
            mode="metadata_http",
            label="List models",
            method="GET",
            endpoint_hint="/models",
            description="Checks credentials against the Gemini model list; it never calls generateContent.",
        ),
    ),
    # Protocol profiles below share the OpenAI Chat implementation but make a
    # vendor's documented JSON/auth behavior explicit in the static contract.
    # This avoids claiming that every arbitrary compatible gateway supports
    # structured output or even requires a bearer token.
    AdapterDescriptor(
        canonical_key="deepseek_chat",
        kind="llm",
        adapter_class=OpenAIChatCompatibleLLMProvider,
        aliases=("deepseek-chat",),
        capabilities=LLM_CAPABILITIES,
        label="DeepSeek Chat (OpenAI compatible)",
        endpoint_mode="base_url",
        endpoint_hint="https://api.deepseek.com/v1",
        config_fields=(
            AdapterConfigField("json_mode", "JSON mode", "select", default="response_format", options=("response_format", "prompt_only")),
            AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="bearer", options=("bearer",)),
        ),
        docs_url="https://api-docs.deepseek.com/",
        test_strategy=AdapterTestStrategy(mode="metadata_http", label="List models", method="GET", endpoint_hint="/models", description="Uses provider metadata only; it never creates a completion."),
    ),
    AdapterDescriptor(
        canonical_key="qwen_chat",
        kind="llm",
        adapter_class=OpenAIChatCompatibleLLMProvider,
        aliases=("qwen-chat", "dashscope_chat", "dashscope-chat"),
        capabilities=LLM_CAPABILITIES,
        label="Qwen / DashScope Chat (OpenAI compatible)",
        endpoint_mode="base_url",
        endpoint_hint="https://dashscope.aliyuncs.com/compatible-mode/v1",
        config_fields=(
            AdapterConfigField("json_mode", "JSON mode", "select", default="response_format", options=("response_format", "prompt_only")),
            AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="bearer", options=("bearer",)),
        ),
        docs_url="https://help.aliyun.com/en/model-studio/qwen-structured-output",
        test_strategy=AdapterTestStrategy(mode="metadata_http", label="List models", method="GET", endpoint_hint="/models", description="Uses provider metadata only; it never creates a completion."),
    ),
    AdapterDescriptor(
        canonical_key="ollama_chat",
        kind="llm",
        adapter_class=OpenAIChatCompatibleLLMProvider,
        aliases=("ollama-chat", "ollama"),
        capabilities=LLM_CAPABILITIES,
        label="Ollama OpenAI-compatible Chat",
        endpoint_mode="base_url",
        endpoint_hint="http://localhost:11434/v1",
        required_fields=("base_url", "model_name"),
        config_fields=(
            AdapterConfigField("json_mode", "JSON mode", "select", default="response_format", options=("response_format", "prompt_only")),
            AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="none", options=("none", "bearer")),
        ),
        docs_url="https://docs.ollama.com/api/openai-compatibility",
        test_strategy=AdapterTestStrategy(mode="metadata_http", label="List local models", method="GET", endpoint_hint="/models", description="Uses local model metadata only; it never creates a completion."),
    ),
    AdapterDescriptor(
        canonical_key="vllm_chat",
        kind="llm",
        adapter_class=OpenAIChatCompatibleLLMProvider,
        aliases=("vllm-chat", "vllm"),
        capabilities=LLM_CAPABILITIES,
        label="vLLM OpenAI-compatible Chat",
        endpoint_mode="base_url",
        endpoint_hint="http://localhost:8000/v1",
        required_fields=("base_url", "model_name"),
        config_fields=(
            AdapterConfigField("json_mode", "JSON mode", "select", default="response_format", options=("response_format", "json_schema", "prompt_only")),
            AdapterConfigField("json_schema_name", "JSON schema name", default="response"),
            AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="none", options=("none", "bearer")),
        ),
        docs_url="https://docs.vllm.ai/en/stable/serving/openai_compatible_server/",
        test_strategy=AdapterTestStrategy(mode="metadata_http", label="List served models", method="GET", endpoint_hint="/models", description="Uses server metadata only; it never creates a completion."),
    ),
    AdapterDescriptor(
        canonical_key="azure_openai",
        kind="llm",
        adapter_class=OpenAIResponsesLLMProvider,
        aliases=("azure-openai",),
        capabilities=LLM_CAPABILITIES,
        label="Azure OpenAI Responses API",
        endpoint_mode="base_url",
        endpoint_hint="https://your-resource.openai.azure.com/openai/v1  (model is the deployment name)",
        config_fields=(
            AdapterConfigField("json_mode", "JSON mode", "select", default="json_object", options=("json_object", "json_schema", "prompt_only")),
            AdapterConfigField("json_schema_name", "JSON schema name", default="response"),
            AdapterConfigField("max_output_tokens", "Maximum output tokens", "number", placeholder="1024"),
            AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="api-key", options=("api-key", "bearer")),
        ),
        docs_url="https://learn.microsoft.com/azure/ai-foundry/openai/reference-preview-latest",
        test_strategy=AdapterTestStrategy(mode="metadata_http", label="List deployments", method="GET", endpoint_hint="/models", description="Uses provider metadata only; it never creates a response."),
    ),
    AdapterDescriptor(
        canonical_key="mimo_chat",
        kind="llm",
        adapter_class=OpenAIChatCompatibleLLMProvider,
        aliases=("mimo-chat",),
        capabilities=TEXT_ONLY_CAPABILITIES,
        label="MiMo Chat (text-only profile)",
        endpoint_mode="base_url",
        endpoint_hint="https://api.xiaomimimo.com/v1",
        config_fields=(
            AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="bearer", options=("bearer", "api-key")),
        ),
        docs_url="https://api.xiaomimimo.com/",
        test_strategy=AdapterTestStrategy(mode="configuration", label="Configuration validation", description="No MiMo metadata endpoint is assumed; no completion request is sent."),
    ),
    AdapterDescriptor(
        canonical_key="openai_chat_text",
        kind="llm",
        adapter_class=OpenAIChatCompatibleLLMProvider,
        aliases=("openai-chat-text", "compatible-text"),
        capabilities=TEXT_ONLY_CAPABILITIES,
        label="OpenAI-compatible Chat (text-only profile)",
        endpoint_mode="base_url",
        endpoint_hint="Provider API base URL ending in /v1",
        config_fields=(
            AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="bearer", options=("bearer", "api-key", "none")),
        ),
        docs_url="https://platform.openai.com/docs/api-reference/chat",
        test_strategy=AdapterTestStrategy(mode="configuration", label="Configuration validation", description="Use this safe profile when a compatible endpoint has no documented JSON mode."),
    ),
)


for _descriptor in LLM_ADAPTER_DESCRIPTORS:
    register_adapter(_descriptor)


__all__ = ["LLM_ADAPTER_DESCRIPTORS", "LLM_CAPABILITIES", "TEXT_ONLY_CAPABILITIES"]
