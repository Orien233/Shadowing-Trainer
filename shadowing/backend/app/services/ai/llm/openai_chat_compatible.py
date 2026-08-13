"""Canonical name for the established OpenAI Chat Completions adapter."""

from app.services.ai.llm.openai_compatible import OpenAICompatibleLLMProvider


# Keep the legacy class (and therefore old imports and type names) intact while
# making the protocol-specific canonical name available to the adapter catalog.
OpenAIChatCompatibleLLMProvider = OpenAICompatibleLLMProvider


__all__ = ["OpenAIChatCompatibleLLMProvider", "OpenAICompatibleLLMProvider"]
