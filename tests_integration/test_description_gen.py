"""End-to-end integration tests for LLM-powered description generation."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

from auto_mcp import AutoMCP
from auto_mcp.core.generator import GeneratorConfig, MCPGenerator
from auto_mcp.llm.ollama import OllamaProvider
from auto_mcp.prompts.templates import FALLBACK_DESCRIPTIONS

pytestmark = pytest.mark.integration


def _create_temp_module(tmp_path: Path, code: str, name: str = "sample") -> ModuleType:
    """Write code to a temp file and import it as a module."""
    module_file = tmp_path / f"{name}.py"
    module_file.write_text(textwrap.dedent(code))

    import importlib.util

    spec = importlib.util.spec_from_file_location(name, module_file)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TestGenerateToolsWithLLM:
    """Test MCPGenerator.analyze_and_generate with a real Ollama model."""

    @pytest.mark.asyncio
    async def test_tools_get_llm_descriptions(
        self,
        ollama_provider: OllamaProvider,
        tmp_path: Path,
    ) -> None:
        """Tools generated with LLM have descriptions beyond the fallback."""
        module = _create_temp_module(
            tmp_path,
            """\
            def multiply(x: int, y: int) -> int:
                \"\"\"Multiply two integers.\"\"\"
                return x * y
            """,
            name="math_ops",
        )

        config = GeneratorConfig(
            server_name="test-llm",
            use_llm=True,
            use_cache=False,
        )
        generator = MCPGenerator(llm=ollama_provider, config=config)
        tools, _, _ = await generator.analyze_and_generate([module])

        assert len(tools) >= 1
        tool = tools[0]

        # The LLM description should not be the generic fallback
        generic_fallback = FALLBACK_DESCRIPTIONS["tool"].format(name="multiply")
        assert tool.description != generic_fallback, (
            f"Description is the generic fallback: {tool.description!r}"
        )
        assert len(tool.description.strip()) > 0

    @pytest.mark.asyncio
    async def test_multiple_functions_get_unique_descriptions(
        self,
        ollama_provider: OllamaProvider,
        tmp_path: Path,
    ) -> None:
        """Different functions receive distinct descriptions."""
        module = _create_temp_module(
            tmp_path,
            """\
            def add(a: int, b: int) -> int:
                \"\"\"Add two numbers.\"\"\"
                return a + b

            def concatenate(first: str, second: str) -> str:
                \"\"\"Concatenate two strings.\"\"\"
                return first + second

            def is_even(n: int) -> bool:
                \"\"\"Check whether a number is even.\"\"\"
                return n % 2 == 0
            """,
            name="mixed_utils",
        )

        config = GeneratorConfig(
            server_name="test-unique",
            use_llm=True,
            use_cache=False,
        )
        generator = MCPGenerator(llm=ollama_provider, config=config)
        tools, _, _ = await generator.analyze_and_generate([module])

        descriptions = [t.description for t in tools]
        assert len(tools) == 3
        # All descriptions should be unique (the LLM produces different text per function)
        assert len(set(descriptions)) == len(descriptions), (
            f"Expected unique descriptions, got: {descriptions}"
        )


class TestGenerateFileWithLLM:
    """Test standalone file generation with real LLM descriptions."""

    def test_generated_file_contains_llm_descriptions(
        self,
        ollama_model: str,
        tmp_path: Path,
    ) -> None:
        """The generated server file includes LLM-produced docstrings."""
        module = _create_temp_module(
            tmp_path,
            """\
            def greet(name: str) -> str:
                \"\"\"Generate a greeting message for the given name.\"\"\"
                return f"Hello, {name}!"
            """,
            name="greeter",
        )

        auto = AutoMCP(
            llm_provider="ollama",
            llm_model=ollama_model,
            use_llm=True,
            use_cache=False,
            server_name="greet-server",
        )

        output = tmp_path / "greet_server.py"
        result = auto.generate_file([module], output)

        content = result.read_text()
        assert "@mcp.tool" in content

        # The docstring in the generated file should not be the raw fallback
        generic_fallback = FALLBACK_DESCRIPTIONS["tool"].format(name="greet")
        assert generic_fallback not in content, (
            "Generated file contains the generic fallback instead of LLM description"
        )


class TestAutoMCPWithOllama:
    """Test the high-level AutoMCP API with a real Ollama backend."""

    @pytest.mark.asyncio
    async def test_analyze_with_llm(
        self,
        ollama_model: str,
        tmp_path: Path,
    ) -> None:
        """AutoMCP.analyze produces tools with LLM descriptions."""
        module = _create_temp_module(
            tmp_path,
            """\
            def divide(a: float, b: float) -> float:
                \"\"\"Divide a by b.\"\"\"
                if b == 0:
                    raise ValueError("Cannot divide by zero")
                return a / b
            """,
            name="division",
        )

        auto = AutoMCP(
            llm_provider="ollama",
            llm_model=ollama_model,
            use_llm=True,
            use_cache=False,
        )
        tools, _, _ = await auto.analyze([module])

        assert len(tools) >= 1
        desc = tools[0].description
        assert isinstance(desc, str)
        assert len(desc.strip()) > 0
