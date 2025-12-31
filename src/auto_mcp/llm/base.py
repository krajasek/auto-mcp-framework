"""Base protocol for LLM providers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from auto_mcp.core.analyzer import MethodMetadata


@runtime_checkable
class LLMProvider(Protocol):
    """Abstract interface for LLM providers.

    All LLM providers must implement this protocol to be compatible
    with auto-mcp. This allows swapping between Ollama, OpenAI, and
    Anthropic providers transparently.
    """

    @property
    def model_name(self) -> str:
        """Get the name of the model being used."""
        ...

    @property
    def provider_name(self) -> str:
        """Get the name of the provider (e.g., 'ollama', 'openai')."""
        ...

    async def generate_tool_description(
        self,
        method: MethodMetadata,
        context: str | None = None,
    ) -> str:
        """Generate a description for an MCP tool.

        Args:
            method: The method metadata to generate a description for
            context: Optional additional context about the module/project

        Returns:
            A concise, clear description suitable for an MCP tool
        """
        ...

    async def generate_parameter_descriptions(
        self,
        method: MethodMetadata,
    ) -> dict[str, str]:
        """Generate descriptions for method parameters.

        Args:
            method: The method metadata containing parameters

        Returns:
            Dictionary mapping parameter names to descriptions
        """
        ...

    async def generate_resource_description(
        self,
        method: MethodMetadata,
        uri_template: str,
    ) -> str:
        """Generate a description for an MCP resource.

        Args:
            method: The method metadata for the resource function
            uri_template: The URI template for the resource

        Returns:
            A description suitable for an MCP resource
        """
        ...

    async def generate_prompt_template(
        self,
        method: MethodMetadata,
    ) -> str:
        """Generate a description for an MCP prompt.

        Args:
            method: The method metadata for the prompt function

        Returns:
            A description for the MCP prompt
        """
        ...

    def shutdown(self) -> None:
        """Release any resources held by the provider."""
        ...


class BaseLLMProvider:
    """Base class with common functionality for LLM providers.

    Provides default implementations and shared utilities that concrete
    providers can use or override.
    """

    def __init__(self, model: str) -> None:
        """Initialize the base provider.

        Args:
            model: The model name/identifier to use
        """
        self._model = model

    @property
    def model_name(self) -> str:
        """Get the model name."""
        return self._model

    def _build_tool_prompt(self, method: MethodMetadata, context: str | None) -> str:
        """Build the prompt for tool description generation.

        Args:
            method: The method metadata
            context: Optional additional context

        Returns:
            The formatted prompt string
        """
        from auto_mcp.prompts.templates import TOOL_DESCRIPTION_PROMPT

        return TOOL_DESCRIPTION_PROMPT.format(
            function_name=method.name,
            signature=str(method.signature),
            docstring=method.docstring or "No docstring provided",
            source_code=method.source_code[:1000] if method.source_code else "N/A",
            context=context or "No additional context",
        )

    def _build_parameter_prompt(self, method: MethodMetadata) -> str:
        """Build the prompt for parameter description generation.

        Args:
            method: The method metadata

        Returns:
            The formatted prompt string
        """
        from auto_mcp.prompts.templates import PARAMETER_DESCRIPTION_PROMPT

        params_info = "\n".join(
            f"- {p['name']}: {p['type_str']}"
            + (f" (default: {p['default']})" if p["has_default"] else "")
            for p in method.parameters
        )

        return PARAMETER_DESCRIPTION_PROMPT.format(
            function_name=method.name,
            docstring=method.docstring or "No docstring provided",
            parameters=params_info or "No parameters",
        )

    def _build_resource_prompt(
        self, method: MethodMetadata, uri_template: str
    ) -> str:
        """Build the prompt for resource description generation.

        Args:
            method: The method metadata
            uri_template: The URI template

        Returns:
            The formatted prompt string
        """
        from auto_mcp.prompts.templates import RESOURCE_DESCRIPTION_PROMPT

        return RESOURCE_DESCRIPTION_PROMPT.format(
            function_name=method.name,
            uri_template=uri_template,
            docstring=method.docstring or "No docstring provided",
            return_type=method.return_type or "Any",
        )

    def _build_prompt_template_prompt(self, method: MethodMetadata) -> str:
        """Build the prompt for MCP prompt description generation.

        Args:
            method: The method metadata

        Returns:
            The formatted prompt string
        """
        from auto_mcp.prompts.templates import PROMPT_TEMPLATE_PROMPT

        return PROMPT_TEMPLATE_PROMPT.format(
            function_name=method.name,
            docstring=method.docstring or "No docstring provided",
            parameters=", ".join(p["name"] for p in method.parameters),
        )

    def _parse_parameter_response(self, response: str) -> dict[str, str]:
        """Parse LLM response into parameter descriptions.

        Expects format like:
        - param_name: description
        - other_param: description

        Args:
            response: The raw LLM response

        Returns:
            Dictionary of parameter names to descriptions
        """
        descriptions: dict[str, str] = {}

        for line in response.strip().split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                line = line[2:]

            if ":" in line:
                name, desc = line.split(":", 1)
                name = name.strip().strip("`")
                desc = desc.strip()
                if name and desc:
                    descriptions[name] = desc

        return descriptions

    def shutdown(self) -> None:
        """Default shutdown implementation (no-op)."""
        pass
