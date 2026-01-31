"""Shared fixtures for Ollama integration tests."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from auto_mcp.core.analyzer import MethodMetadata
from auto_mcp.llm.ollama import OllamaProvider


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --ollama-model CLI option."""
    parser.addoption(
        "--ollama-model",
        action="store",
        default="qwen2.5-coder:7b",
        help="Ollama model to use for integration tests (default: qwen2.5-coder:7b)",
    )


@pytest.fixture(scope="session")
def ollama_model(request: pytest.FixtureRequest) -> str:
    """Get the Ollama model name from CLI option."""
    return str(request.config.getoption("--ollama-model"))


@pytest.fixture(scope="session", autouse=True)
def ollama_available() -> None:
    """Check that Ollama is running, skip all tests if not."""
    try:
        import ollama

        ollama.list()
    except Exception:
        pytest.skip("Ollama is not running — skipping integration tests", allow_module_level=True)


@pytest.fixture
def ollama_provider(ollama_model: str) -> OllamaProvider:
    """Create an OllamaProvider with the user-specified model."""
    return OllamaProvider(model=ollama_model)


@pytest.fixture
def sample_method_metadata() -> MethodMetadata:
    """Create sample method metadata from a simple function."""

    def add(a: int, b: int) -> int:
        """Add two numbers and return the result."""
        return a + b

    return MethodMetadata(
        name="add",
        qualified_name="add",
        module_name="sample",
        signature=inspect.signature(add),
        docstring="Add two numbers and return the result.",
        type_hints={"a": int, "b": int, "return": int},
        return_type=int,
        is_async=False,
        is_method=False,
        is_classmethod=False,
        is_staticmethod=False,
        source_code="def add(a: int, b: int) -> int:\n    return a + b",
        decorators=[],
        parameters=[
            {
                "name": "a",
                "kind": "POSITIONAL_OR_KEYWORD",
                "has_default": False,
                "default": None,
                "type": int,
                "type_str": "int",
            },
            {
                "name": "b",
                "kind": "POSITIONAL_OR_KEYWORD",
                "has_default": False,
                "default": None,
                "type": int,
                "type_str": "int",
            },
        ],
        mcp_metadata={},
    )


@pytest.fixture
def complex_method_metadata() -> MethodMetadata:
    """Create metadata for a more complex function with defaults and docstring."""

    def search_records(
        query: str,
        limit: int = 10,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        """Search records in the database matching the given query.

        Performs a full-text search across all indexed fields and returns
        matching records sorted by relevance score.

        Args:
            query: The search query string
            limit: Maximum number of results to return
            offset: Number of results to skip for pagination
            include_archived: Whether to include archived records

        Returns:
            A list of matching record dictionaries
        """
        return []

    return MethodMetadata(
        name="search_records",
        qualified_name="search_records",
        module_name="database",
        signature=inspect.signature(search_records),
        docstring=inspect.getdoc(search_records),
        type_hints={
            "query": str,
            "limit": int,
            "offset": int,
            "include_archived": bool,
            "return": list[dict[str, Any]],
        },
        return_type=list[dict[str, Any]],
        is_async=False,
        is_method=False,
        is_classmethod=False,
        is_staticmethod=False,
        source_code=inspect.getsource(search_records),
        decorators=[],
        parameters=[
            {
                "name": "query",
                "kind": "POSITIONAL_OR_KEYWORD",
                "has_default": False,
                "default": None,
                "type": str,
                "type_str": "str",
            },
            {
                "name": "limit",
                "kind": "POSITIONAL_OR_KEYWORD",
                "has_default": True,
                "default": 10,
                "type": int,
                "type_str": "int",
            },
            {
                "name": "offset",
                "kind": "POSITIONAL_OR_KEYWORD",
                "has_default": True,
                "default": 0,
                "type": int,
                "type_str": "int",
            },
            {
                "name": "include_archived",
                "kind": "POSITIONAL_OR_KEYWORD",
                "has_default": True,
                "default": False,
                "type": bool,
                "type_str": "bool",
            },
        ],
        mcp_metadata={},
    )
