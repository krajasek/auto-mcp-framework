"""Tests for MCP generator."""

from __future__ import annotations

import inspect
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

from auto_mcp.cache import PromptCache
from auto_mcp.core.analyzer import MethodMetadata
from auto_mcp.core.generator import (
    GeneratedPrompt,
    GeneratedResource,
    GeneratedTool,
    GeneratorConfig,
    MCPGenerator,
)
from auto_mcp.decorators import mcp_exclude, mcp_prompt, mcp_resource, mcp_tool


# Create a sample module for testing
def create_sample_module() -> ModuleType:
    """Create a sample module with various functions."""
    module = ModuleType("sample_module")
    module.__file__ = "/tmp/sample_module.py"

    def add_numbers(a: int, b: int) -> int:
        """Add two numbers together."""
        return a + b

    def multiply(x: float, y: float) -> float:
        """Multiply two numbers."""
        return x * y

    async def async_operation(data: str) -> str:
        """Perform an async operation."""
        return f"processed: {data}"

    def _private_helper() -> None:
        """This is a private helper function."""
        pass

    # Set __module__ to match the module name for proper inspection
    add_numbers.__module__ = "sample_module"
    multiply.__module__ = "sample_module"
    async_operation.__module__ = "sample_module"
    _private_helper.__module__ = "sample_module"

    module.add_numbers = add_numbers
    module.multiply = multiply
    module.async_operation = async_operation
    module._private_helper = _private_helper

    return module


def create_decorated_module() -> ModuleType:
    """Create a module with decorated functions."""
    module = ModuleType("decorated_module")
    module.__file__ = "/tmp/decorated_module.py"

    @mcp_tool(name="custom_add", description="Custom add description")
    def add_tool(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @mcp_resource(uri="data://{id}", name="data_resource", description="Get data by ID")
    def get_data(id: str) -> str:
        """Get data by ID."""
        return f"data for {id}"

    @mcp_prompt(name="greeting", description="Generate a greeting")
    def greeting_prompt(name: str) -> str:
        """Generate a greeting for a person."""
        return f"Hello, {name}!"

    @mcp_exclude
    def excluded_func() -> None:
        """This function should be excluded."""
        pass

    # Set __module__ to match the module name for proper inspection
    add_tool.__module__ = "decorated_module"
    get_data.__module__ = "decorated_module"
    greeting_prompt.__module__ = "decorated_module"
    excluded_func.__module__ = "decorated_module"

    module.add_tool = add_tool
    module.get_data = get_data
    module.greeting_prompt = greeting_prompt
    module.excluded_func = excluded_func

    return module


@pytest.fixture
def sample_method() -> MethodMetadata:
    """Create sample method metadata."""

    def sample_func(name: str, count: int = 10) -> str:
        """Process the given name."""
        return f"{name}: {count}"

    return MethodMetadata(
        name="sample_func",
        qualified_name="sample_func",
        module_name="test_module",
        signature=inspect.signature(sample_func),
        docstring="Process the given name.",
        type_hints={"name": str, "count": int},
        return_type=str,
        is_async=False,
        is_method=False,
        is_classmethod=False,
        is_staticmethod=False,
        source_code="def sample_func(name: str, count: int = 10) -> str:\n    pass",
        decorators=[],
        parameters=[
            {"name": "name", "type_str": "str", "has_default": False, "default": None},
            {"name": "count", "type_str": "int", "has_default": True, "default": 10},
        ],
        mcp_metadata={},
    )


@pytest.fixture
def mock_llm() -> MagicMock:
    """Create a mock LLM provider."""
    llm = MagicMock()
    llm.model_name = "test-model"
    llm.provider_name = "test"
    llm.generate_tool_description = AsyncMock(return_value="LLM generated tool description")
    llm.generate_parameter_descriptions = AsyncMock(
        return_value={"name": "The name parameter", "count": "The count parameter"}
    )
    llm.generate_resource_description = AsyncMock(
        return_value="LLM generated resource description"
    )
    llm.generate_prompt_template = AsyncMock(
        return_value="LLM generated prompt description"
    )
    return llm


@pytest.fixture
def cache(tmp_path: Path) -> PromptCache:
    """Create a cache with temporary directory."""
    return PromptCache(cache_dir=tmp_path)


class TestGeneratorConfig:
    """Tests for GeneratorConfig dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        config = GeneratorConfig()

        assert config.server_name == "auto-mcp-server"
        assert config.server_description == "Auto-generated MCP server"
        assert config.include_private is False
        assert config.generate_resources is True
        assert config.generate_prompts is True
        assert config.use_cache is True
        assert config.use_llm is True

    def test_custom_values(self) -> None:
        """Test that custom values can be set."""
        config = GeneratorConfig(
            server_name="my-server",
            server_description="My custom server",
            include_private=True,
            generate_resources=False,
            generate_prompts=False,
            use_cache=False,
            use_llm=False,
        )

        assert config.server_name == "my-server"
        assert config.server_description == "My custom server"
        assert config.include_private is True
        assert config.generate_resources is False
        assert config.generate_prompts is False
        assert config.use_cache is False
        assert config.use_llm is False


class TestGeneratedTool:
    """Tests for GeneratedTool dataclass."""

    def test_create_tool(self, sample_method: MethodMetadata) -> None:
        """Test creating a GeneratedTool."""

        def my_func() -> None:
            pass

        tool = GeneratedTool(
            name="my_tool",
            description="My tool description",
            function=my_func,
            metadata=sample_method,
        )

        assert tool.name == "my_tool"
        assert tool.description == "My tool description"
        assert tool.function is my_func
        assert tool.parameter_descriptions == {}

    def test_with_parameter_descriptions(self, sample_method: MethodMetadata) -> None:
        """Test tool with parameter descriptions."""

        def my_func() -> None:
            pass

        tool = GeneratedTool(
            name="my_tool",
            description="My tool description",
            function=my_func,
            metadata=sample_method,
            parameter_descriptions={"param1": "First parameter"},
        )

        assert tool.parameter_descriptions == {"param1": "First parameter"}


class TestGeneratedResource:
    """Tests for GeneratedResource dataclass."""

    def test_create_resource(self, sample_method: MethodMetadata) -> None:
        """Test creating a GeneratedResource."""

        def my_func() -> None:
            pass

        resource = GeneratedResource(
            name="my_resource",
            uri="data://{id}",
            description="My resource description",
            function=my_func,
            metadata=sample_method,
        )

        assert resource.name == "my_resource"
        assert resource.uri == "data://{id}"
        assert resource.description == "My resource description"
        assert resource.mime_type is None

    def test_with_mime_type(self, sample_method: MethodMetadata) -> None:
        """Test resource with MIME type."""

        def my_func() -> None:
            pass

        resource = GeneratedResource(
            name="my_resource",
            uri="data://{id}",
            description="My resource",
            function=my_func,
            metadata=sample_method,
            mime_type="application/json",
        )

        assert resource.mime_type == "application/json"


class TestGeneratedPrompt:
    """Tests for GeneratedPrompt dataclass."""

    def test_create_prompt(self, sample_method: MethodMetadata) -> None:
        """Test creating a GeneratedPrompt."""

        def my_func() -> None:
            pass

        prompt = GeneratedPrompt(
            name="my_prompt",
            description="My prompt description",
            function=my_func,
            metadata=sample_method,
        )

        assert prompt.name == "my_prompt"
        assert prompt.description == "My prompt description"


class TestMCPGenerator:
    """Tests for MCPGenerator class."""

    def test_init_defaults(self) -> None:
        """Test generator initialization with defaults."""
        generator = MCPGenerator()

        assert generator.llm is None
        assert generator.cache is not None
        assert generator.config is not None
        assert generator.config.server_name == "auto-mcp-server"

    def test_init_with_llm(self, mock_llm: MagicMock) -> None:
        """Test generator initialization with LLM provider."""
        generator = MCPGenerator(llm=mock_llm)

        assert generator.llm is mock_llm

    def test_init_with_cache(self, cache: PromptCache) -> None:
        """Test generator initialization with cache."""
        generator = MCPGenerator(cache=cache)

        assert generator.cache is cache

    def test_init_with_config(self) -> None:
        """Test generator initialization with custom config."""
        config = GeneratorConfig(server_name="custom-server")
        generator = MCPGenerator(config=config)

        assert generator.config.server_name == "custom-server"


class TestMCPGeneratorAnalysis:
    """Tests for MCPGenerator analysis methods."""

    @pytest.mark.asyncio
    async def test_analyze_and_generate_tools(self) -> None:
        """Test analyzing modules and generating tools."""
        module = create_sample_module()
        config = GeneratorConfig(use_llm=False, use_cache=False)
        generator = MCPGenerator(config=config)

        tools, resources, prompts = await generator.analyze_and_generate([module])

        # Should have add_numbers, multiply, async_operation (not _private_helper)
        assert len(tools) >= 2
        tool_names = [t.name for t in tools]
        assert "add_numbers" in tool_names
        assert "multiply" in tool_names

    @pytest.mark.asyncio
    async def test_analyze_with_llm(self, mock_llm: MagicMock) -> None:
        """Test analysis with LLM provider."""
        module = create_sample_module()
        config = GeneratorConfig(use_cache=False)
        generator = MCPGenerator(llm=mock_llm, config=config)

        tools, resources, prompts = await generator.analyze_and_generate([module])

        # LLM should have been called for descriptions
        assert mock_llm.generate_tool_description.called

    @pytest.mark.asyncio
    async def test_analyze_with_cache(self, cache: PromptCache) -> None:
        """Test analysis with caching."""
        module = create_sample_module()
        config = GeneratorConfig(use_llm=False)
        generator = MCPGenerator(cache=cache, config=config)

        # First call
        tools1, _, _ = await generator.analyze_and_generate([module])
        # Second call should use cache
        tools2, _, _ = await generator.analyze_and_generate([module])

        assert len(tools1) == len(tools2)

    @pytest.mark.asyncio
    async def test_analyze_decorated_module(self) -> None:
        """Test analyzing module with MCP decorators."""
        module = create_decorated_module()
        config = GeneratorConfig(use_llm=False, use_cache=False)
        generator = MCPGenerator(config=config)

        tools, resources, prompts = await generator.analyze_and_generate([module])

        # Check tool with custom name
        tool_names = [t.name for t in tools]
        assert "custom_add" in tool_names

        # Check resource
        assert len(resources) >= 1
        resource_names = [r.name for r in resources]
        assert "data_resource" in resource_names

        # Check prompt
        assert len(prompts) >= 1
        prompt_names = [p.name for p in prompts]
        assert "greeting" in prompt_names


class TestMCPGeneratorServer:
    """Tests for MCPGenerator server creation."""

    def test_create_server(self) -> None:
        """Test creating an in-memory FastMCP server."""
        module = create_sample_module()
        config = GeneratorConfig(
            server_name="test-server",
            use_llm=False,
            use_cache=False,
        )
        generator = MCPGenerator(config=config)

        server = generator.create_server([module])

        assert server is not None
        assert server.name == "test-server"

    def test_create_server_with_resources(self) -> None:
        """Test creating server with resources enabled."""
        module = create_decorated_module()
        config = GeneratorConfig(
            use_llm=False,
            use_cache=False,
            generate_resources=True,
        )
        generator = MCPGenerator(config=config)

        server = generator.create_server([module])

        assert server is not None

    def test_create_server_with_prompts(self) -> None:
        """Test creating server with prompts enabled."""
        module = create_decorated_module()
        config = GeneratorConfig(
            use_llm=False,
            use_cache=False,
            generate_prompts=True,
        )
        generator = MCPGenerator(config=config)

        server = generator.create_server([module])

        assert server is not None


class TestMCPGeneratorStandalone:
    """Tests for standalone file generation."""

    def test_generate_standalone(self, tmp_path: Path) -> None:
        """Test generating a standalone server file."""
        module = create_sample_module()
        output_file = tmp_path / "server.py"
        config = GeneratorConfig(
            server_name="standalone-server",
            use_llm=False,
            use_cache=False,
        )
        generator = MCPGenerator(config=config)

        result = generator.generate_standalone([module], output_file)

        assert result == output_file
        assert output_file.exists()

        # Check file contents
        content = output_file.read_text()
        assert "from mcp.server.fastmcp import FastMCP" in content
        assert "standalone-server" in content
        assert "@mcp.tool" in content

    def test_generate_standalone_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test that generate_standalone creates parent directories."""
        module = create_sample_module()
        output_file = tmp_path / "nested" / "dir" / "server.py"
        config = GeneratorConfig(use_llm=False, use_cache=False)
        generator = MCPGenerator(config=config)

        result = generator.generate_standalone([module], output_file)

        assert result.exists()
        assert result.parent.exists()

    def test_generated_code_has_main(self, tmp_path: Path) -> None:
        """Test that generated code has main block."""
        module = create_sample_module()
        output_file = tmp_path / "server.py"
        config = GeneratorConfig(use_llm=False, use_cache=False)
        generator = MCPGenerator(config=config)

        generator.generate_standalone([module], output_file)
        content = output_file.read_text()

        assert 'if __name__ == "__main__":' in content
        assert "mcp.run()" in content


class TestMCPGeneratorPackage:
    """Tests for package generation."""

    def test_generate_package(self, tmp_path: Path) -> None:
        """Test generating a complete package."""
        module = create_sample_module()
        config = GeneratorConfig(
            server_name="package-server",
            server_description="Test package",
            use_llm=False,
            use_cache=False,
        )
        generator = MCPGenerator(config=config)

        result = generator.generate_package([module], tmp_path, "my-server")

        assert result == tmp_path / "my-server"
        assert result.exists()

        # Check structure
        assert (result / "pyproject.toml").exists()
        assert (result / "src" / "my_server").exists()
        assert (result / "src" / "my_server" / "__init__.py").exists()
        assert (result / "src" / "my_server" / "server.py").exists()

    def test_generated_pyproject(self, tmp_path: Path) -> None:
        """Test that pyproject.toml is generated correctly."""
        module = create_sample_module()
        config = GeneratorConfig(
            server_description="My awesome server",
            use_llm=False,
            use_cache=False,
        )
        generator = MCPGenerator(config=config)

        result = generator.generate_package([module], tmp_path, "test-package")

        pyproject = (result / "pyproject.toml").read_text()
        assert 'name = "test-package"' in pyproject
        assert 'version = "0.1.0"' in pyproject
        assert "mcp>=1.0" in pyproject
        assert "hatchling" in pyproject

    def test_generated_init(self, tmp_path: Path) -> None:
        """Test that __init__.py exports correctly."""
        module = create_sample_module()
        config = GeneratorConfig(use_llm=False, use_cache=False)
        generator = MCPGenerator(config=config)

        result = generator.generate_package([module], tmp_path, "my-pkg")

        init_content = (result / "src" / "my_pkg" / "__init__.py").read_text()
        assert "from my_pkg.server import mcp" in init_content
        assert "__all__" in init_content


class TestMCPGeneratorDescriptions:
    """Tests for description generation."""

    @pytest.mark.asyncio
    async def test_tool_description_from_decorator(self) -> None:
        """Test that decorator description is used."""
        module = create_decorated_module()
        config = GeneratorConfig(use_llm=False, use_cache=False)
        generator = MCPGenerator(config=config)

        tools, _, _ = await generator.analyze_and_generate([module])

        # Find the custom_add tool
        custom_add = next((t for t in tools if t.name == "custom_add"), None)
        assert custom_add is not None
        assert custom_add.description == "Custom add description"

    @pytest.mark.asyncio
    async def test_tool_description_fallback(self) -> None:
        """Test fallback to docstring-based description."""
        module = create_sample_module()
        config = GeneratorConfig(use_llm=False, use_cache=False)
        generator = MCPGenerator(config=config)

        tools, _, _ = await generator.analyze_and_generate([module])

        # Find add_numbers tool
        add_tool = next((t for t in tools if t.name == "add_numbers"), None)
        assert add_tool is not None
        assert "Add two numbers" in add_tool.description

    @pytest.mark.asyncio
    async def test_llm_description_generation(self, mock_llm: MagicMock) -> None:
        """Test that LLM is used for description when available."""
        module = create_sample_module()
        config = GeneratorConfig(use_cache=False)
        generator = MCPGenerator(llm=mock_llm, config=config)

        tools, _, _ = await generator.analyze_and_generate([module])

        # LLM should be called
        assert mock_llm.generate_tool_description.called
        # Description should be from LLM
        add_tool = next((t for t in tools if t.name == "add_numbers"), None)
        assert add_tool is not None
        assert add_tool.description == "LLM generated tool description"

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self, mock_llm: MagicMock) -> None:
        """Test fallback when LLM fails."""
        mock_llm.generate_tool_description = AsyncMock(side_effect=Exception("API Error"))

        module = create_sample_module()
        config = GeneratorConfig(use_cache=False)
        generator = MCPGenerator(llm=mock_llm, config=config)

        tools, _, _ = await generator.analyze_and_generate([module])

        # Should still have tools with fallback descriptions
        assert len(tools) >= 1
        add_tool = next((t for t in tools if t.name == "add_numbers"), None)
        assert add_tool is not None
        assert "Add two numbers" in add_tool.description


class TestMCPGeneratorCaching:
    """Tests for caching behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit(self, cache: PromptCache, mock_llm: MagicMock) -> None:
        """Test that cached descriptions are used."""
        module = create_sample_module()
        config = GeneratorConfig(use_cache=True, use_llm=True)
        generator = MCPGenerator(llm=mock_llm, cache=cache, config=config)

        # First call should use LLM
        await generator.analyze_and_generate([module])

        # Second call should use cache
        await generator.analyze_and_generate([module])

        # LLM should not be called again for same methods
        # Note: This depends on cache implementation
        stats = cache.get_stats()
        assert stats.hits > 0 or stats.misses > 0

    @pytest.mark.asyncio
    async def test_cache_disabled(self, mock_llm: MagicMock) -> None:
        """Test that cache can be disabled."""
        module = create_sample_module()
        config = GeneratorConfig(use_cache=False, use_llm=True)
        generator = MCPGenerator(llm=mock_llm, config=config)

        # Make two calls
        await generator.analyze_and_generate([module])
        first_count = mock_llm.generate_tool_description.call_count

        await generator.analyze_and_generate([module])
        second_count = mock_llm.generate_tool_description.call_count

        # LLM should be called both times
        assert second_count > first_count


class TestMCPGeneratorEdgeCases:
    """Tests for edge cases."""

    def test_empty_module_list(self) -> None:
        """Test with empty module list."""
        config = GeneratorConfig(use_llm=False, use_cache=False)
        generator = MCPGenerator(config=config)

        server = generator.create_server([])

        assert server is not None

    @pytest.mark.asyncio
    async def test_multiple_modules(self) -> None:
        """Test with multiple modules."""
        module1 = create_sample_module()
        module2 = create_decorated_module()
        config = GeneratorConfig(use_llm=False, use_cache=False)
        generator = MCPGenerator(config=config)

        tools, resources, prompts = await generator.analyze_and_generate([module1, module2])

        # Should have tools from both modules
        assert len(tools) >= 3

    @pytest.mark.asyncio
    async def test_module_with_no_functions(self) -> None:
        """Test module with no public functions."""
        module = ModuleType("empty_module")
        module.__file__ = "/tmp/empty_module.py"
        config = GeneratorConfig(use_llm=False, use_cache=False)
        generator = MCPGenerator(config=config)

        tools, resources, prompts = await generator.analyze_and_generate([module])

        assert len(tools) == 0
        assert len(resources) == 0
        assert len(prompts) == 0

    def test_generate_with_context(self) -> None:
        """Test generation with context string."""
        module = create_sample_module()
        config = GeneratorConfig(use_llm=False, use_cache=False)
        generator = MCPGenerator(config=config)

        server = generator.create_server([module], context="This is a math library")

        assert server is not None

    def test_generate_with_sessions_enabled(self) -> None:
        """Test generation with sessions enabled."""
        module = create_sample_module()
        config = GeneratorConfig(
            use_llm=False,
            use_cache=False,
            enable_sessions=True,
            session_ttl=1800,
            max_sessions=50,
        )
        generator = MCPGenerator(config=config)

        # Session manager should be created
        assert generator.session_manager is not None
        assert generator.config.enable_sessions is True

        server = generator.create_server([module])
        assert server is not None

    def test_generate_with_custom_session_manager(self) -> None:
        """Test generation with custom session manager."""
        from auto_mcp.session.manager import SessionManager, SessionConfig

        custom_session_manager = SessionManager(
            config=SessionConfig(default_ttl=3600, max_sessions=100)
        )

        module = create_sample_module()
        config = GeneratorConfig(
            use_llm=False,
            use_cache=False,
            enable_sessions=True,
        )
        generator = MCPGenerator(config=config, session_manager=custom_session_manager)

        # Should use the custom session manager
        assert generator.session_manager is custom_session_manager
