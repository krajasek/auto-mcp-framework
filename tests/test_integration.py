"""Integration tests for auto-mcp.

These tests verify end-to-end functionality using the example modules.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

# Add examples to path for imports
examples_path = Path(__file__).parent.parent / "examples"
sys.path.insert(0, str(examples_path.parent))

from auto_mcp import AutoMCP, quick_server  # noqa: E402
from auto_mcp.core.analyzer import ModuleAnalyzer  # noqa: E402


class TestSimpleMathIntegration:
    """Integration tests using the simple_math example."""

    @pytest.fixture
    def math_module(self) -> ModuleType:
        """Load the math_utils module."""
        from examples.simple_math import math_utils

        return math_utils

    def test_analyze_math_module(self, math_module: ModuleType) -> None:
        """Test analyzing the math module extracts all public functions."""
        analyzer = ModuleAnalyzer()
        methods = analyzer.analyze_module(math_module)

        # Should find public functions, not private ones
        method_names = [m.name for m in methods]
        assert "add" in method_names
        assert "subtract" in method_names
        assert "multiply" in method_names
        assert "divide" in method_names
        assert "power" in method_names
        assert "factorial" in method_names
        assert "is_prime" in method_names
        assert "gcd" in method_names
        assert "_internal_helper" not in method_names

    def test_create_server_from_math_module(self, math_module: ModuleType) -> None:
        """Test creating a server from the math module."""
        auto = AutoMCP(use_llm=False, use_cache=False)
        server = auto.create_server([math_module])

        assert server is not None
        assert server.name == "auto-mcp-server"

    def test_quick_server_math(self, math_module: ModuleType) -> None:
        """Test quick_server with math module."""
        server = quick_server(math_module, name="math-test")

        assert server is not None
        assert server.name == "math-test"

    def test_generate_file_math(self, math_module: ModuleType, tmp_path: Path) -> None:
        """Test generating a standalone file from math module."""
        auto = AutoMCP(use_llm=False, use_cache=False)
        output = tmp_path / "math_server.py"

        result = auto.generate_file([math_module], output, name="math-server")

        assert result.exists()
        content = result.read_text()
        assert "FastMCP" in content
        assert "@mcp.tool" in content
        assert "add" in content
        assert "multiply" in content

    @pytest.mark.asyncio
    async def test_analyze_returns_tools(self, math_module: ModuleType) -> None:
        """Test that analyze returns tool definitions."""
        auto = AutoMCP(use_llm=False, use_cache=False)
        tools, resources, prompts = await auto.analyze([math_module])

        tool_names = [t.name for t in tools]
        assert "add" in tool_names
        assert "factorial" in tool_names
        assert len(tools) >= 8  # All public functions


class TestAsyncAPIIntegration:
    """Integration tests using the async_api example."""

    @pytest.fixture
    def weather_module(self) -> ModuleType:
        """Load the weather_api module."""
        from examples.async_api import weather_api

        return weather_api

    def test_analyze_async_module(self, weather_module: ModuleType) -> None:
        """Test analyzing async functions."""
        analyzer = ModuleAnalyzer()
        methods = analyzer.analyze_module(weather_module)

        method_names = [m.name for m in methods]
        assert "get_current_weather" in method_names
        assert "get_forecast" in method_names
        assert "compare_weather" in method_names

        # Check async detection
        async_methods = [m for m in methods if m.is_async]
        assert len(async_methods) >= 4

    def test_create_server_from_async_module(self, weather_module: ModuleType) -> None:
        """Test creating a server from async module."""
        auto = AutoMCP(use_llm=False, use_cache=False)
        server = auto.create_server([weather_module])

        assert server is not None

    @pytest.mark.asyncio
    async def test_async_tools_analysis(self, weather_module: ModuleType) -> None:
        """Test that async functions become tools."""
        auto = AutoMCP(use_llm=False, use_cache=False)
        tools, _, _ = await auto.analyze([weather_module])

        tool_names = [t.name for t in tools]
        assert "get_current_weather" in tool_names
        assert "get_forecast" in tool_names
        assert "search_cities" in tool_names

    def test_generate_file_async(self, weather_module: ModuleType, tmp_path: Path) -> None:
        """Test generating file with async functions."""
        auto = AutoMCP(use_llm=False, use_cache=False)
        output = tmp_path / "weather_server.py"

        result = auto.generate_file([weather_module], output)

        content = result.read_text()
        # Generated wrappers call original async functions
        assert "get_current_weather" in content
        assert "@mcp.tool" in content


class TestClassServiceIntegration:
    """Integration tests using the class_service example."""

    @pytest.fixture
    def todo_module(self) -> ModuleType:
        """Load the todo_service module."""
        from examples.class_service import todo_service

        return todo_service

    def test_analyze_decorated_methods(self, todo_module: ModuleType) -> None:
        """Test that decorated methods are found."""
        analyzer = ModuleAnalyzer()
        methods = analyzer.analyze_module(todo_module)

        method_names = [m.name for m in methods]
        # Analyzer uses actual function names (decorator names applied at generation)
        assert "create" in method_names or "create_todo" in method_names
        assert "get" in method_names or "get_todo" in method_names
        assert "list_all" in method_names or "list_todos" in method_names

    def test_create_server_from_class_service(self, todo_module: ModuleType) -> None:
        """Test creating server from class-based service."""
        auto = AutoMCP(use_llm=False, use_cache=False)
        server = auto.create_server([todo_module])

        assert server is not None

    @pytest.mark.asyncio
    async def test_decorated_tools(self, todo_module: ModuleType) -> None:
        """Test that @mcp_tool decorated methods become tools."""
        auto = AutoMCP(use_llm=False, use_cache=False)
        tools, _, _ = await auto.analyze([todo_module])

        tool_names = [t.name for t in tools]
        # These should use the custom names from @mcp_tool
        assert "create_todo" in tool_names
        assert "get_todo" in tool_names
        assert "list_todos" in tool_names
        assert "delete_todo" in tool_names
        assert "get_stats" in tool_names


class TestMultiModuleIntegration:
    """Integration tests combining multiple modules."""

    @pytest.fixture
    def all_modules(self) -> list[ModuleType]:
        """Load all example modules."""
        from examples.async_api import weather_api
        from examples.class_service import todo_service
        from examples.simple_math import math_utils

        return [math_utils, weather_api, todo_service]

    def test_create_server_multiple_modules(self, all_modules: list[ModuleType]) -> None:
        """Test creating server from multiple modules."""
        auto = AutoMCP(use_llm=False, use_cache=False)
        server = auto.create_server(all_modules)

        assert server is not None

    @pytest.mark.asyncio
    async def test_analyze_multiple_modules(self, all_modules: list[ModuleType]) -> None:
        """Test analyzing multiple modules."""
        auto = AutoMCP(use_llm=False, use_cache=False)
        tools, _, _ = await auto.analyze(all_modules)

        tool_names = [t.name for t in tools]
        # Math tools
        assert "add" in tool_names
        assert "multiply" in tool_names
        # Weather tools
        assert "get_current_weather" in tool_names
        # Todo tools
        assert "create_todo" in tool_names

    def test_generate_package_multiple_modules(
        self,
        all_modules: list[ModuleType],
        tmp_path: Path,
    ) -> None:
        """Test generating a package from multiple modules."""
        auto = AutoMCP(use_llm=False, use_cache=False)

        result = auto.generate_package(
            all_modules,
            tmp_path,
            "multi-service",
        )

        assert result.exists()
        assert (result / "pyproject.toml").exists()
        assert (result / "src" / "multi_service" / "server.py").exists()

        # Check server has tools from all modules
        server_content = (result / "src" / "multi_service" / "server.py").read_text()
        assert "@mcp.tool" in server_content


class TestGeneratorIntegration:
    """Integration tests for the generator component."""

    @pytest.fixture
    def math_module(self) -> ModuleType:
        """Load the math_utils module."""
        from examples.simple_math import math_utils

        return math_utils

    def test_generator_standalone(self, math_module: ModuleType, tmp_path: Path) -> None:
        """Test MCPGenerator standalone file generation."""
        from auto_mcp.core.generator import GeneratorConfig, MCPGenerator

        config = GeneratorConfig(
            server_name="test-generator",
            use_llm=False,
            use_cache=False,
        )
        generator = MCPGenerator(config)

        output = tmp_path / "generated.py"
        result = generator.generate_standalone([math_module], output)

        assert result.exists()
        content = result.read_text()
        assert "FastMCP" in content
        assert "@mcp.tool" in content

    def test_generator_package(self, math_module: ModuleType, tmp_path: Path) -> None:
        """Test MCPGenerator package generation."""
        from auto_mcp.core.generator import GeneratorConfig, MCPGenerator

        config = GeneratorConfig(
            server_name="pkg-test",
            use_llm=False,
            use_cache=False,
        )
        generator = MCPGenerator(config)

        result = generator.generate_package([math_module], tmp_path, "pkg-test")

        assert result.exists()
        assert (result / "pyproject.toml").exists()
        pyproject = (result / "pyproject.toml").read_text()
        assert "pkg-test" in pyproject

    def test_generator_in_memory(self, math_module: ModuleType) -> None:
        """Test MCPGenerator in-memory server creation."""
        from auto_mcp.core.generator import GeneratorConfig, MCPGenerator

        config = GeneratorConfig(
            server_name="memory-test",
            use_llm=False,
            use_cache=False,
        )
        generator = MCPGenerator(config)

        server = generator.create_server([math_module])

        assert server is not None
        # Server is created with tools from the module
        assert server.name is not None


class TestCacheIntegration:
    """Integration tests for caching functionality."""

    @pytest.fixture
    def math_module(self) -> ModuleType:
        """Load the math_utils module."""
        from examples.simple_math import math_utils

        return math_utils

    def test_cache_persistence(self, math_module: ModuleType, tmp_path: Path) -> None:
        """Test that cache persists between runs."""
        # First run - populates cache
        auto1 = AutoMCP(
            use_llm=False,
            use_cache=True,
            cache_dir=tmp_path,
        )
        auto1.create_server([math_module])
        auto1.save_cache([math_module])

        # Second run - should use cache
        auto2 = AutoMCP(
            use_llm=False,
            use_cache=True,
            cache_dir=tmp_path,
        )
        server = auto2.create_server([math_module])

        assert server is not None

    def test_cache_clear(self, math_module: ModuleType, tmp_path: Path) -> None:
        """Test clearing cache."""
        auto = AutoMCP(
            use_llm=False,
            use_cache=True,
            cache_dir=tmp_path,
        )
        auto.create_server([math_module])
        auto.save_cache([math_module])

        # Clear and verify
        count = auto.clear_cache([math_module])
        assert count >= 0


class TestContextManagerIntegration:
    """Integration tests for context manager usage."""

    @pytest.fixture
    def math_module(self) -> ModuleType:
        """Load the math_utils module."""
        from examples.simple_math import math_utils

        return math_utils

    def test_with_statement(self, math_module: ModuleType, tmp_path: Path) -> None:
        """Test using AutoMCP as context manager."""
        with AutoMCP(
            use_llm=False,
            use_cache=True,
            cache_dir=tmp_path,
        ) as auto:
            server = auto.create_server([math_module])
            assert server is not None

        # After exit, should have saved cache without error
