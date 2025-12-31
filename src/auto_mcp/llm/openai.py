"""OpenAI LLM provider implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from openai import AsyncOpenAI

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


class OpenAIProvider(BaseLLMProvider):
    """LLM provider using OpenAI API.

    This provider uses the OpenAI API to generate descriptions
    using models like gpt-4o-mini, gpt-4o, etc.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the OpenAI provider.

        Args:
            model: The OpenAI model to use (default: gpt-4o-mini)
            api_key: Optional API key (defaults to OPENAI_API_KEY env var)
            base_url: Optional custom base URL for API-compatible services
            timeout: Request timeout in seconds
        """
        super().__init__(model)
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._client: AsyncOpenAI | None = None

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "openai"

    def _get_client(self) -> AsyncOpenAI:
        """Get or create the async client.

        Returns:
            The OpenAI async client
        """
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    async def _generate(self, prompt: str) -> str:
        """Generate a response from OpenAI.

        Args:
            prompt: The prompt to send

        Returns:
            The generated response text
        """
        client = self._get_client()

        response = await client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=200,
        )

        content = response.choices[0].message.content
        return content.strip() if content else ""

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
        if self._client is not None:
            # AsyncOpenAI doesn't have a close method, just clear the reference
            self._client = None
