"""Integration tests for OllamaProvider against a real Ollama instance."""

from __future__ import annotations

import pytest

from auto_mcp.core.analyzer import MethodMetadata
from auto_mcp.llm.ollama import OllamaProvider


pytestmark = pytest.mark.integration


class TestOllamaToolDescription:
    """Tests for tool description generation."""

    @pytest.mark.asyncio
    async def test_generate_tool_description(
        self,
        ollama_provider: OllamaProvider,
        sample_method_metadata: MethodMetadata,
    ) -> None:
        """LLM returns a non-empty tool description."""
        result = await ollama_provider.generate_tool_description(sample_method_metadata)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    @pytest.mark.asyncio
    async def test_description_is_concise(
        self,
        ollama_provider: OllamaProvider,
        sample_method_metadata: MethodMetadata,
    ) -> None:
        """Generated description is under 100 words per the prompt guidelines."""
        result = await ollama_provider.generate_tool_description(sample_method_metadata)
        word_count = len(result.split())
        assert word_count <= 100, f"Description has {word_count} words, expected <= 100"

    @pytest.mark.asyncio
    async def test_description_avoids_forbidden_phrases(
        self,
        ollama_provider: OllamaProvider,
        sample_method_metadata: MethodMetadata,
    ) -> None:
        """Description follows the system prompt guideline to avoid 'This function...'."""
        result = await ollama_provider.generate_tool_description(sample_method_metadata)
        lower = result.lower()
        assert not lower.startswith("this function"), (
            f"Description starts with 'This function...': {result!r}"
        )
        assert not lower.startswith("this method"), (
            f"Description starts with 'This method...': {result!r}"
        )

    @pytest.mark.asyncio
    async def test_description_with_context(
        self,
        ollama_provider: OllamaProvider,
        sample_method_metadata: MethodMetadata,
    ) -> None:
        """Providing context still produces a valid description."""
        result = await ollama_provider.generate_tool_description(
            sample_method_metadata,
            context="This is part of a math utilities library.",
        )
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    @pytest.mark.asyncio
    async def test_complex_function_description(
        self,
        ollama_provider: OllamaProvider,
        complex_method_metadata: MethodMetadata,
    ) -> None:
        """LLM handles a complex function with multiple parameters."""
        result = await ollama_provider.generate_tool_description(complex_method_metadata)
        assert isinstance(result, str)
        assert len(result.strip()) > 0


class TestOllamaParameterDescriptions:
    """Tests for parameter description generation."""

    @pytest.mark.asyncio
    async def test_generate_parameter_descriptions(
        self,
        ollama_provider: OllamaProvider,
        sample_method_metadata: MethodMetadata,
    ) -> None:
        """LLM returns descriptions for all parameters."""
        result = await ollama_provider.generate_parameter_descriptions(
            sample_method_metadata,
        )
        assert isinstance(result, dict)
        assert "a" in result
        assert "b" in result

    @pytest.mark.asyncio
    async def test_parameter_descriptions_are_nonempty(
        self,
        ollama_provider: OllamaProvider,
        sample_method_metadata: MethodMetadata,
    ) -> None:
        """Each parameter description is a non-empty string."""
        result = await ollama_provider.generate_parameter_descriptions(
            sample_method_metadata,
        )
        for name, desc in result.items():
            assert isinstance(desc, str), f"Description for '{name}' is not a string"
            assert len(desc.strip()) > 0, f"Description for '{name}' is empty"

    @pytest.mark.asyncio
    async def test_complex_parameter_descriptions_cover_all(
        self,
        ollama_provider: OllamaProvider,
        complex_method_metadata: MethodMetadata,
    ) -> None:
        """All parameters of a complex function get descriptions."""
        result = await ollama_provider.generate_parameter_descriptions(
            complex_method_metadata,
        )
        expected_params = {"query", "limit", "offset", "include_archived"}
        assert expected_params.issubset(result.keys()), (
            f"Missing params: {expected_params - result.keys()}"
        )


class TestOllamaResourceDescription:
    """Tests for resource description generation."""

    @pytest.mark.asyncio
    async def test_generate_resource_description(
        self,
        ollama_provider: OllamaProvider,
        sample_method_metadata: MethodMetadata,
    ) -> None:
        """LLM returns a valid resource description."""
        result = await ollama_provider.generate_resource_description(
            sample_method_metadata,
            uri_template="math://add/{a}/{b}",
        )
        assert isinstance(result, str)
        assert len(result.strip()) > 0


class TestOllamaPromptTemplate:
    """Tests for prompt template description generation."""

    @pytest.mark.asyncio
    async def test_generate_prompt_template(
        self,
        ollama_provider: OllamaProvider,
        sample_method_metadata: MethodMetadata,
    ) -> None:
        """LLM returns a valid prompt template description."""
        result = await ollama_provider.generate_prompt_template(sample_method_metadata)
        assert isinstance(result, str)
        assert len(result.strip()) > 0
