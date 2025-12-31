"""Ollama LLM provider implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import ollama

from auto_mcp.llm.base import BaseLLMProvider
from auto_mcp.prompts.templates import (
    SYSTEM_PROMPT,
    get_fallback_parameter_description,
    get_fallback_prompt_description,
    get_fallback_resource_description,
    get_fallback_tool_description,
)

if TYPE_CHECKING:
    from auto_mcp.core.analyzer import MethodMetadata


class OllamaProvider(BaseLLMProvider):
    """LLM provider using Ollama for local model inference.

    This provider connects to a local Ollama instance to generate
    descriptions using models like qwen2.5-coder, codellama, etc.
    """

    def __init__(
        self,
        model: str = "qwen2.5-coder:7b",
        host: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the Ollama provider.

        Args:
            model: The Ollama model to use (default: qwen2.5-coder:7b)
            host: Optional custom Ollama host URL
            timeout: Request timeout in seconds
        """
        super().__init__(model)
        self._host = host
        self._timeout = timeout
        self._client: ollama.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "ollama"

    def _get_client(self) -> ollama.AsyncClient:
        """Get or create the async client.

        Returns:
            The Ollama async client
        """
        if self._client is None:
            if self._host:
                self._client = ollama.AsyncClient(host=self._host)
            else:
                self._client = ollama.AsyncClient()
        return self._client

    async def _generate(self, prompt: str) -> str:
        """Generate a response from Ollama.

        Args:
            prompt: The prompt to send

        Returns:
            The generated response text
        """
        client = self._get_client()

        response = await client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            options={
                "temperature": 0.3,  # Lower temperature for more consistent output
                "num_predict": 200,  # Limit response length
            },
        )

        return str(response["message"]["content"]).strip()

    async def generate_tool_description(
        self,
        method: MethodMetadata,
        context: str | None = None,
    ) -> str:
        """Generate a description for an MCP tool.

        Args:
            method: The method metadata
            context: Optional additional context

        Returns:
            The generated description
        """
        try:
            prompt = self._build_tool_prompt(method, context)
            return await self._generate(prompt)
        except Exception:
            # Fall back to docstring-based description
            return get_fallback_tool_description(method.name, method.docstring)

    async def generate_parameter_descriptions(
        self,
        method: MethodMetadata,
    ) -> dict[str, str]:
        """Generate descriptions for method parameters.

        Args:
            method: The method metadata

        Returns:
            Dictionary of parameter names to descriptions
        """
        if not method.parameters:
            return {}

        try:
            prompt = self._build_parameter_prompt(method)
            response = await self._generate(prompt)
            descriptions = self._parse_parameter_response(response)

            # Fill in any missing parameters with fallbacks
            for param in method.parameters:
                name = param["name"]
                if name not in descriptions:
                    descriptions[name] = get_fallback_parameter_description(name)

            return descriptions
        except Exception:
            # Fall back to basic descriptions
            return {
                p["name"]: get_fallback_parameter_description(p["name"])
                for p in method.parameters
            }

    async def generate_resource_description(
        self,
        method: MethodMetadata,
        uri_template: str,
    ) -> str:
        """Generate a description for an MCP resource.

        Args:
            method: The method metadata
            uri_template: The URI template

        Returns:
            The generated description
        """
        try:
            prompt = self._build_resource_prompt(method, uri_template)
            return await self._generate(prompt)
        except Exception:
            return get_fallback_resource_description(method.name, method.docstring)

    async def generate_prompt_template(
        self,
        method: MethodMetadata,
    ) -> str:
        """Generate a description for an MCP prompt.

        Args:
            method: The method metadata

        Returns:
            The generated description
        """
        try:
            prompt = self._build_prompt_template_prompt(method)
            return await self._generate(prompt)
        except Exception:
            return get_fallback_prompt_description(method.name, method.docstring)

    def shutdown(self) -> None:
        """Clean up the client."""
        self._client = None
