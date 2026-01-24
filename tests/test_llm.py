"""Tests for LLM providers."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auto_mcp.core.analyzer import MethodMetadata
from auto_mcp.llm import (
    AnthropicProvider,
    LLMProvider,
    OllamaProvider,
    OpenAIProvider,
    create_provider,
)
from auto_mcp.llm.base import BaseLLMProvider as BaseProvider
from auto_mcp.prompts.templates import (
    get_fallback_parameter_description,
    get_fallback_prompt_description,
    get_fallback_resource_description,
    get_fallback_tool_description,
)


@pytest.fixture
def sample_method_metadata() -> MethodMetadata:
    """Create sample method metadata for testing."""

    def sample_func(name: str, count: int = 10) -> str:
        """Process the given name and return a formatted string."""
        return f"{name}: {count}"

    return MethodMetadata(
        name="sample_func",
        qualified_name="sample_func",
        module_name="test_module",
        signature=inspect.signature(sample_func),
        docstring="Process the given name and return a formatted string.",
        type_hints={"name": str, "count": int},
        return_type=str,
        is_async=False,
        is_method=False,
        is_classmethod=False,
        is_staticmethod=False,
        source_code=(
            "def sample_func(name: str, count: int = 10) -> str:\n"
            "    return f'{name}: {count}'"
        ),
        decorators=[],
        parameters=[
            {
                "name": "name",
                "kind": "POSITIONAL_OR_KEYWORD",
                "has_default": False,
                "default": None,
                "type": str,
                "type_str": "str",
            },
            {
                "name": "count",
                "kind": "POSITIONAL_OR_KEYWORD",
                "has_default": True,
                "default": 10,
                "type": int,
                "type_str": "int",
            },
        ],
        mcp_metadata={},
    )


class TestLLMProviderProtocol:
    """Tests for LLMProvider protocol."""

    def test_ollama_implements_protocol(self) -> None:
        """Test that OllamaProvider implements LLMProvider protocol."""
        provider = OllamaProvider()
        assert isinstance(provider, LLMProvider)

    def test_openai_implements_protocol(self) -> None:
        """Test that OpenAIProvider implements LLMProvider protocol."""
        provider = OpenAIProvider()
        assert isinstance(provider, LLMProvider)

    def test_anthropic_implements_protocol(self) -> None:
        """Test that AnthropicProvider implements LLMProvider protocol."""
        provider = AnthropicProvider()
        assert isinstance(provider, LLMProvider)


class TestBaseLLMProvider:
    """Tests for BaseLLMProvider."""

    def test_model_name(self) -> None:
        """Test model_name property."""
        provider = BaseProvider("test-model")
        assert provider.model_name == "test-model"

    def test_build_tool_prompt(
        self, sample_method_metadata: MethodMetadata
    ) -> None:
        """Test tool prompt building."""
        provider = BaseProvider("test-model")
        prompt = provider._build_tool_prompt(sample_method_metadata, "Test context")

        assert "sample_func" in prompt
        assert "Process the given name" in prompt
        assert "Test context" in prompt

    def test_build_parameter_prompt(
        self, sample_method_metadata: MethodMetadata
    ) -> None:
        """Test parameter prompt building."""
        provider = BaseProvider("test-model")
        prompt = provider._build_parameter_prompt(sample_method_metadata)

        assert "sample_func" in prompt
        assert "name" in prompt
        assert "count" in prompt

    def test_parse_parameter_response(self) -> None:
        """Test parsing parameter descriptions from LLM response."""
        provider = BaseProvider("test-model")

        response = """
- name: The name to process
- count: Number of times to repeat
"""
        result = provider._parse_parameter_response(response)

        assert result["name"] == "The name to process"
        assert result["count"] == "Number of times to repeat"

    def test_parse_parameter_response_with_asterisks(self) -> None:
        """Test parsing with asterisk bullets."""
        provider = BaseProvider("test-model")

        response = """
* param1: First parameter description
* param2: Second parameter description
"""
        result = provider._parse_parameter_response(response)

        assert result["param1"] == "First parameter description"
        assert result["param2"] == "Second parameter description"

    def test_shutdown_is_noop(self) -> None:
        """Test that shutdown is a no-op by default."""
        provider = BaseProvider("test-model")
        # Should not raise
        provider.shutdown()

    def test_build_resource_prompt(
        self, sample_method_metadata: MethodMetadata
    ) -> None:
        """Test resource prompt building."""
        provider = BaseProvider("test-model")
        prompt = provider._build_resource_prompt(
            sample_method_metadata, "resource://{name}"
        )

        assert "sample_func" in prompt
        assert "resource://{name}" in prompt
        assert "Process the given name" in prompt

    def test_build_prompt_template_prompt(
        self, sample_method_metadata: MethodMetadata
    ) -> None:
        """Test prompt template prompt building."""
        provider = BaseProvider("test-model")
        prompt = provider._build_prompt_template_prompt(sample_method_metadata)

        assert "sample_func" in prompt
        assert "Process the given name" in prompt


class TestOllamaProvider:
    """Tests for OllamaProvider."""

    def test_init_defaults(self) -> None:
        """Test default initialization."""
        provider = OllamaProvider()
        assert provider.model_name == "qwen2.5-coder:7b"
        assert provider.provider_name == "ollama"

    def test_init_custom_model(self) -> None:
        """Test initialization with custom model."""
        provider = OllamaProvider(model="codellama:7b")
        assert provider.model_name == "codellama:7b"

    def test_init_custom_host(self) -> None:
        """Test initialization with custom host."""
        provider = OllamaProvider(host="http://localhost:11435")
        assert provider._host == "http://localhost:11435"

    @pytest.mark.asyncio
    async def test_generate_tool_description_success(
        self, sample_method_metadata: MethodMetadata
    ) -> None:
        """Test successful tool description generation."""
        provider = OllamaProvider()

        mock_response = {"message": {"content": "Processes a name and returns formatted output."}}
        with patch.object(provider, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await provider.generate_tool_description(sample_method_metadata)

            assert result == "Processes a name and returns formatted output."
            mock_client.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_tool_description_fallback(
        self, sample_method_metadata: MethodMetadata
    ) -> None:
        """Test fallback when LLM fails."""
        provider = OllamaProvider()

        with patch.object(provider, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.side_effect = Exception("Connection error")
            mock_get_client.return_value = mock_client

            result = await provider.generate_tool_description(sample_method_metadata)

            # Should return fallback based on docstring
            assert "Process the given name" in result

    @pytest.mark.asyncio
    async def test_generate_parameter_descriptions(
        self, sample_method_metadata: MethodMetadata
    ) -> None:
        """Test parameter description generation."""
        provider = OllamaProvider()

        mock_response = {
            "message": {"content": "- name: The name to format\n- count: Repeat count"}
        }
        with patch.object(provider, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await provider.generate_parameter_descriptions(sample_method_metadata)

            assert "name" in result
            assert "count" in result

    def test_shutdown(self) -> None:
        """Test shutdown clears client."""
        provider = OllamaProvider()
        provider._client = MagicMock()  # Simulate initialized client
        provider.shutdown()
        assert provider._client is None


class TestOpenAIProvider:
    """Tests for OpenAIProvider."""

    def test_init_defaults(self) -> None:
        """Test default initialization."""
        provider = OpenAIProvider()
        assert provider.model_name == "gpt-4o-mini"
        assert provider.provider_name == "openai"

    def test_init_custom_model(self) -> None:
        """Test initialization with custom model."""
        provider = OpenAIProvider(model="gpt-4o")
        assert provider.model_name == "gpt-4o"

    def test_init_with_api_key(self) -> None:
        """Test initialization with API key."""
        provider = OpenAIProvider(api_key="sk-test-key")
        assert provider._api_key == "sk-test-key"

    @pytest.mark.asyncio
    async def test_generate_tool_description_success(
        self, sample_method_metadata: MethodMetadata
    ) -> None:
        """Test successful tool description generation."""
        provider = OpenAIProvider()

        mock_message = MagicMock()
        mock_message.content = "Formats a name with the given count."
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch.object(provider, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await provider.generate_tool_description(sample_method_metadata)

            assert result == "Formats a name with the given count."

    @pytest.mark.asyncio
    async def test_generate_tool_description_fallback(
        self, sample_method_metadata: MethodMetadata
    ) -> None:
        """Test fallback when API fails."""
        provider = OpenAIProvider()

        with patch.object(provider, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create.side_effect = Exception("API error")
            mock_get_client.return_value = mock_client

            result = await provider.generate_tool_description(sample_method_metadata)

            assert "Process the given name" in result


class TestAnthropicProvider:
    """Tests for AnthropicProvider."""

    def test_init_defaults(self) -> None:
        """Test default initialization."""
        provider = AnthropicProvider()
        assert provider.model_name == "claude-3-haiku-20240307"
        assert provider.provider_name == "anthropic"

    def test_init_custom_model(self) -> None:
        """Test initialization with custom model."""
        provider = AnthropicProvider(model="claude-3-sonnet-20240229")
        assert provider.model_name == "claude-3-sonnet-20240229"

    @pytest.mark.asyncio
    async def test_generate_tool_description_success(
        self, sample_method_metadata: MethodMetadata
    ) -> None:
        """Test successful tool description generation."""
        provider = AnthropicProvider()

        mock_block = MagicMock()
        mock_block.text = "Processes names with optional count."
        mock_response = MagicMock()
        mock_response.content = [mock_block]

        with patch.object(provider, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await provider.generate_tool_description(sample_method_metadata)

            assert result == "Processes names with optional count."


class TestCreateProvider:
    """Tests for create_provider factory function."""

    def test_create_ollama(self) -> None:
        """Test creating Ollama provider."""
        provider = create_provider("ollama")
        assert isinstance(provider, OllamaProvider)
        assert provider.model_name == "qwen2.5-coder:7b"

    def test_create_ollama_custom_model(self) -> None:
        """Test creating Ollama provider with custom model."""
        provider = create_provider("ollama", model="codellama:7b")
        assert provider.model_name == "codellama:7b"

    def test_create_openai(self) -> None:
        """Test creating OpenAI provider."""
        provider = create_provider("openai")
        assert isinstance(provider, OpenAIProvider)
        assert provider.model_name == "gpt-4o-mini"

    def test_create_openai_with_key(self) -> None:
        """Test creating OpenAI provider with API key."""
        provider = create_provider("openai", api_key="sk-test")
        assert isinstance(provider, OpenAIProvider)

    def test_create_anthropic(self) -> None:
        """Test creating Anthropic provider."""
        provider = create_provider("anthropic")
        assert isinstance(provider, AnthropicProvider)
        assert provider.model_name == "claude-3-haiku-20240307"

    def test_create_unknown_raises(self) -> None:
        """Test that unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown provider"):
            create_provider("unknown")  # type: ignore[arg-type]


class TestFallbackDescriptions:
    """Tests for fallback description functions."""

    def test_tool_fallback_with_docstring(self) -> None:
        """Test tool fallback uses docstring first sentence."""
        result = get_fallback_tool_description(
            "my_func", "This is the first sentence. And more details."
        )
        assert result == "This is the first sentence."

    def test_tool_fallback_without_docstring(self) -> None:
        """Test tool fallback without docstring."""
        result = get_fallback_tool_description("my_func", None)
        assert "my_func" in result

    def test_resource_fallback_with_docstring(self) -> None:
        """Test resource fallback uses docstring."""
        result = get_fallback_resource_description("get_data", "Fetches data from source.")
        assert result == "Fetches data from source."

    def test_prompt_fallback(self) -> None:
        """Test prompt fallback."""
        result = get_fallback_prompt_description("greeting", "Generates a greeting.")
        assert result == "Generates a greeting."

    def test_parameter_fallback(self) -> None:
        """Test parameter fallback makes readable name."""
        result = get_fallback_parameter_description("user_name")
        assert "user name" in result

    def test_resource_fallback_no_docstring(self) -> None:
        """Test resource fallback when no docstring provided."""
        result = get_fallback_resource_description("my_resource", None)
        assert "my_resource" in result

    def test_prompt_fallback_no_docstring(self) -> None:
        """Test prompt fallback when no docstring provided."""
        result = get_fallback_prompt_description("my_prompt", None)
        assert "my_prompt" in result
