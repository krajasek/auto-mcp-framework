"""LLM provider integrations for auto-mcp."""

from typing import Literal

from auto_mcp.llm.anthropic import AnthropicProvider
from auto_mcp.llm.base import BaseLLMProvider, LLMProvider
from auto_mcp.llm.ollama import OllamaProvider
from auto_mcp.llm.openai import OpenAIProvider

__all__ = [
    "LLMProvider",
    "BaseLLMProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "create_provider",
]


def create_provider(
    provider: Literal["ollama", "openai", "anthropic"],
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> LLMProvider:
    """Create an LLM provider instance.

    Args:
        provider: The provider type to create
        model: Optional model name (uses provider default if not specified)
        api_key: Optional API key for cloud providers
        base_url: Optional custom base URL

    Returns:
        An LLM provider instance

    Raises:
        ValueError: If an unknown provider is specified
    """
    if provider == "ollama":
        return OllamaProvider(
            model=model or "qwen2.5-coder:7b",
            host=base_url,
        )
    elif provider == "openai":
        return OpenAIProvider(
            model=model or "gpt-4o-mini",
            api_key=api_key,
            base_url=base_url,
        )
    elif provider == "anthropic":
        return AnthropicProvider(
            model=model or "claude-3-haiku-20240307",
            api_key=api_key,
            base_url=base_url,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")
