"""Tests for the high-level Python API."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from auto_mcp import AutoMCP, quick_server
from auto_mcp.api import AutoMCP as AutoMCPClass


def create_test_module() -> ModuleType:
    """Create a test module with sample functions."""
    module = ModuleType("test_api_module")
    module.__file__ = "/tmp/test_api_module.py"

    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def greet(name: str) -> str:
        """Greet someone."""
        return f"Hello, {name}!"

    async def async_func(data: str) -> str:
        """Async function."""
        return f"processed: {data}"

    # Set __module__ for proper inspection
    add.__module__ = "test_api_module"
    greet.__module__ = "test_api_module"
    async_func.__module__ = "test_api_module"

    module.add = add
    module.greet = greet
    module.async_func = async_func

    return module


class TestAutoMCPInit:
    """Tests for AutoMCP initialization."""

    def test_default_init(self) -> None:
        """Test default initialization."""
        auto = AutoMCP(use_llm=False)

        assert auto.llm_provider is None
        assert auto.config is not None
        assert auto.config.server_name == "auto-mcp-server"

    def test_init_with_server_name(self) -> None:
        """Test initialization with custom server name."""
        auto = AutoMCP(use_llm=False, server_name="my-server")

        assert auto.config.server_name == "my-server"

    def test_init_with_llm_provider(self) -> None:
        """Test initialization with LLM provider."""
        auto = AutoMCP(llm_provider="ollama", llm_model="test-model")

        assert auto.llm_provider is not None
        assert auto.llm_provider.model_name == "test-model"

    def test_init_without_llm(self) -> None:
        """Test initialization without LLM."""
        auto = AutoMCP(use_llm=False)

        assert auto.llm_provider is None
        assert auto.config.use_llm is False

    def test_init_without_cache(self) -> None:
        """Test initialization without cache."""
        auto = AutoMCP(use_llm=False, use_cache=False)

        assert auto.config.use_cache is False

    def test_init_include_private(self) -> None:
        """Test initialization with include_private."""
        auto = AutoMCP(use_llm=False, include_private=True)

        assert auto.config.include_private is True

    def test_init_no_resources(self) -> None:
        """Test initialization without resources."""
        auto = AutoMCP(use_llm=False, generate_resources=False)

        assert auto.config.generate_resources is False

    def test_init_no_prompts(self) -> None:
        """Test initialization without prompts."""
        auto = AutoMCP(use_llm=False, generate_prompts=False)

        assert auto.config.generate_prompts is False


class TestAutoMCPCreateServer:
    """Tests for create_server method."""

    def test_create_server(self) -> None:
        """Test creating a server."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=False)

        server = auto.create_server([module])

        assert server is not None
        assert server.name == "auto-mcp-server"

    def test_create_server_custom_name(self) -> None:
        """Test creating a server with custom name."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=False)

        server = auto.create_server([module], name="custom-server")

        assert server.name == "custom-server"

    def test_create_server_restores_config(self) -> None:
        """Test that config is restored after create_server with custom name."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=False, server_name="original")

        auto.create_server([module], name="temporary")

        assert auto.config.server_name == "original"

    def test_create_server_multiple_modules(self) -> None:
        """Test creating a server from multiple modules."""
        module1 = create_test_module()
        module2 = ModuleType("test_module_2")
        module2.__file__ = "/tmp/test_module_2.py"

        def subtract(a: int, b: int) -> int:
            """Subtract two numbers."""
            return a - b

        subtract.__module__ = "test_module_2"
        module2.subtract = subtract

        auto = AutoMCP(use_llm=False, use_cache=False)
        server = auto.create_server([module1, module2])

        assert server is not None


class TestAutoMCPGenerateFile:
    """Tests for generate_file method."""

    def test_generate_file(self, tmp_path: Path) -> None:
        """Test generating a standalone file."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=False)
        output = tmp_path / "server.py"

        result = auto.generate_file([module], output)

        assert result == output
        assert output.exists()

        content = output.read_text()
        assert "FastMCP" in content
        assert "@mcp.tool" in content

    def test_generate_file_custom_name(self, tmp_path: Path) -> None:
        """Test generating a file with custom server name."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=False)
        output = tmp_path / "server.py"

        auto.generate_file([module], output, name="my-server")

        content = output.read_text()
        assert "my-server" in content

    def test_generate_file_string_path(self, tmp_path: Path) -> None:
        """Test generating a file with string path."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=False)
        output = str(tmp_path / "server.py")

        result = auto.generate_file([module], output)

        assert result.exists()


class TestAutoMCPGeneratePackage:
    """Tests for generate_package method."""

    def test_generate_package(self, tmp_path: Path) -> None:
        """Test generating a package."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=False)

        result = auto.generate_package([module], tmp_path, "my-package")

        assert result == tmp_path / "my-package"
        assert result.exists()
        assert (result / "pyproject.toml").exists()
        assert (result / "src" / "my_package" / "server.py").exists()

    def test_generate_package_string_path(self, tmp_path: Path) -> None:
        """Test generating a package with string path."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=False)

        result = auto.generate_package([module], str(tmp_path), "my-pkg")

        assert result.exists()


class TestAutoMCPAnalyze:
    """Tests for analyze methods."""

    @pytest.mark.asyncio
    async def test_analyze(self) -> None:
        """Test async analyze method."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=False)

        tools, resources, prompts = await auto.analyze([module])

        assert len(tools) >= 2
        tool_names = [t.name for t in tools]
        assert "add" in tool_names
        assert "greet" in tool_names

    def test_analyze_sync(self) -> None:
        """Test sync analyze method."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=False)

        tools, resources, prompts = auto.analyze_sync([module])

        assert len(tools) >= 2


class TestAutoMCPCache:
    """Tests for cache methods."""

    def test_save_cache(self, tmp_path: Path) -> None:
        """Test saving cache."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=True, cache_dir=tmp_path)

        # Generate something to populate cache
        auto.create_server([module])

        # Should not raise
        auto.save_cache([module])

    def test_save_cache_all(self, tmp_path: Path) -> None:
        """Test saving all cache."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=True, cache_dir=tmp_path)

        auto.create_server([module])
        auto.save_cache()  # Save all

    def test_clear_cache(self, tmp_path: Path) -> None:
        """Test clearing cache."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=True, cache_dir=tmp_path)

        auto.create_server([module])
        count = auto.clear_cache([module])

        # Count depends on what was cached
        assert count >= 0

    def test_clear_cache_all(self, tmp_path: Path) -> None:
        """Test clearing all cache."""
        module = create_test_module()
        auto = AutoMCP(use_llm=False, use_cache=True, cache_dir=tmp_path)

        auto.create_server([module])
        count = auto.clear_cache()

        assert count >= 0


class TestAutoMCPContextManager:
    """Tests for context manager functionality."""

    def test_context_manager(self, tmp_path: Path) -> None:
        """Test using AutoMCP as context manager."""
        module = create_test_module()

        with AutoMCP(use_llm=False, use_cache=True, cache_dir=tmp_path) as auto:
            server = auto.create_server([module])
            assert server is not None

        # After exit, should have saved cache (no error)

    def test_shutdown(self) -> None:
        """Test explicit shutdown."""
        auto = AutoMCP(use_llm=False, use_cache=False)

        # Should not raise
        auto.shutdown()


class TestQuickServer:
    """Tests for quick_server convenience function."""

    def test_quick_server(self) -> None:
        """Test quick_server function."""
        module = create_test_module()

        server = quick_server(module)

        assert server is not None
        assert server.name == "auto-mcp-server"

    def test_quick_server_custom_name(self) -> None:
        """Test quick_server with custom name."""
        module = create_test_module()

        server = quick_server(module, name="quick-server")

        assert server.name == "quick-server"

    def test_quick_server_multiple_modules(self) -> None:
        """Test quick_server with multiple modules."""
        module1 = create_test_module()
        module2 = ModuleType("another_module")
        module2.__file__ = "/tmp/another_module.py"

        def func() -> str:
            """A function."""
            return "result"

        func.__module__ = "another_module"
        module2.func = func

        server = quick_server(module1, module2)

        assert server is not None


class TestAutoMCPImports:
    """Tests for package imports."""

    def test_import_from_package(self) -> None:
        """Test importing AutoMCP from package."""
        from auto_mcp import AutoMCP as ImportedAutoMCP

        assert ImportedAutoMCP is AutoMCPClass

    def test_import_quick_server(self) -> None:
        """Test importing quick_server from package."""
        from auto_mcp import quick_server as imported_quick_server

        assert imported_quick_server is quick_server

    def test_all_exports(self) -> None:
        """Test that all expected exports are available."""
        import auto_mcp

        assert hasattr(auto_mcp, "AutoMCP")
        assert hasattr(auto_mcp, "quick_server")
        assert hasattr(auto_mcp, "MCPGenerator")
        assert hasattr(auto_mcp, "GeneratorConfig")
        assert hasattr(auto_mcp, "Settings")
        assert hasattr(auto_mcp, "get_settings")
        assert hasattr(auto_mcp, "mcp_tool")
        assert hasattr(auto_mcp, "mcp_exclude")
        assert hasattr(auto_mcp, "mcp_resource")
        assert hasattr(auto_mcp, "mcp_prompt")


class TestAutoMCPFromPackage:
    """Tests for package-based methods."""

    def test_create_server_from_package(self) -> None:
        """Test creating server from package."""
        auto = AutoMCP(use_llm=False, use_cache=False)

        # Use collections as test package (stdlib, always available)
        server = auto.create_server_from_package("collections")

        assert server is not None

    def test_create_server_from_package_with_name(self) -> None:
        """Test creating server from package with custom name."""
        auto = AutoMCP(use_llm=False, use_cache=False, server_name="original")

        server = auto.create_server_from_package("collections", name="custom-package-server")

        assert server.name == "custom-package-server"
        # Original config should be restored
        assert auto.config.server_name == "original"

    def test_generate_file_from_package(self, tmp_path: Path) -> None:
        """Test generating file from package."""
        auto = AutoMCP(use_llm=False, use_cache=False)
        output = tmp_path / "package_server.py"

        result = auto.generate_file_from_package("collections", output)

        assert result.exists()
        content = result.read_text()
        assert "from mcp.server.fastmcp import FastMCP" in content

    def test_generate_file_from_package_with_name(self, tmp_path: Path) -> None:
        """Test generating file from package with custom name."""
        auto = AutoMCP(use_llm=False, use_cache=False, server_name="original")
        output = tmp_path / "custom_server.py"

        result = auto.generate_file_from_package(
            "collections", output, name="custom-name"
        )

        assert result.exists()
        content = result.read_text()
        assert 'mcp = FastMCP(name="custom-name")' in content
        # Original config should be restored
        assert auto.config.server_name == "original"

    def test_analyze_package(self) -> None:
        """Test analyzing a package."""
        auto = AutoMCP(use_llm=False, use_cache=False)

        metadata = auto.analyze_package("collections")

        assert metadata is not None
        assert metadata.name == "collections"
        assert metadata.module_count >= 1

    @pytest.mark.asyncio
    async def test_analyze_package_async(self) -> None:
        """Test async analyze package."""
        auto = AutoMCP(use_llm=False, use_cache=False)

        tools, resources, prompts = await auto.analyze_package_async("collections")

        # Should have at least some tools
        assert isinstance(tools, list)
        assert isinstance(resources, list)
        assert isinstance(prompts, list)

    def test_analyze_package_sync(self) -> None:
        """Test sync analyze package."""
        auto = AutoMCP(use_llm=False, use_cache=False)

        tools, resources, prompts = auto.analyze_package_sync("collections")

        # Should have at least some tools
        assert isinstance(tools, list)
        assert isinstance(resources, list)
        assert isinstance(prompts, list)


class TestAutoMCPWithLLM:
    """Tests for AutoMCP with LLM integration."""

    def test_with_mock_llm(self) -> None:
        """Test AutoMCP with mocked LLM."""
        # Create with Ollama but we won't actually call it
        auto = AutoMCP(
            llm_provider="ollama",
            llm_model="test-model",
            use_cache=False,
        )

        assert auto.llm_provider is not None
        assert auto.llm_provider.model_name == "test-model"

    def test_llm_provider_shutdown(self) -> None:
        """Test that LLM provider is shut down properly."""
        auto = AutoMCP(
            llm_provider="ollama",
            llm_model="test-model",
        )

        # Shutdown should call provider's shutdown
        auto.shutdown()

        # No error means success


class TestQuickServerFromPackage:
    """Tests for quick_server_from_package function."""

    def test_quick_server_from_package_basic(self) -> None:
        """Test quick_server_from_package creates a server (lines 544-553)."""
        from auto_mcp.api import quick_server_from_package

        # Use json package which is a valid Python package
        server = quick_server_from_package("json", use_llm=False)

        # Should return a FastMCP server
        assert server is not None
