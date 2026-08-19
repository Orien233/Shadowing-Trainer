from app.services.ai.llm.base import LLMProvider
from app.services.ai.llm.openai_chat_compatible import OpenAIChatCompatibleLLMProvider
# Importing the catalog registers only static metadata; it never creates a
# provider or performs a network request.
from app.services.ai.llm.catalog import LLM_ADAPTER_DESCRIPTORS

__all__ = [
    "LLM_ADAPTER_DESCRIPTORS",
    "LLMProvider",
    "OpenAIChatCompatibleLLMProvider",
]
